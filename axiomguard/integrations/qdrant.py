"""
AxiomGuard × Qdrant — Drop-in verified search wrapper.

Usage:
    from qdrant_client import QdrantClient
    from axiomguard import KnowledgeBase
    from axiomguard.integrations.qdrant import VerifiedQdrant

    client = QdrantClient(":memory:")
    kb = KnowledgeBase()
    kb.load("rules/medical.axiom.yml")

    verified = VerifiedQdrant(client, kb=kb, text_field="text")
    results = verified.search(collection_name="docs", query_vector=[...], limit=5)
    # Results are verified — contradictory points annotated or filtered

Requires:
    pip install axiomguard[qdrant]
"""

from __future__ import annotations

from typing import Any, Literal

from axiomguard.integration import verify_chunks
from axiomguard.knowledge_base import KnowledgeBase
from axiomguard.models import Claim


class VerifiedQdrant:
    """Drop-in wrapper around a QdrantClient with AxiomGuard verification.

    Delegates all methods to the underlying client. The ``search()`` method
    adds a post-retrieval verification step.

    Args:
        client: A ``qdrant_client.QdrantClient`` instance.
        kb: A loaded ``KnowledgeBase`` with compiled YAML rules.
        text_field: Payload key containing document text (default: "text").
        mode: Verification mode (default: "annotate").
        axiom_claims: Optional ground-truth facts for every search.
        overfetch_factor: Retrieve this many times ``limit`` to compensate
                          for filtered points (default: 2.0 for filter/strict).
    """

    def __init__(
        self,
        client: Any,
        kb: KnowledgeBase,
        text_field: str = "text",
        mode: Literal["annotate", "filter", "strict"] = "annotate",
        axiom_claims: list[Claim] | None = None,
        overfetch_factor: float = 2.0,
    ) -> None:
        self._client = client
        self._kb = kb
        self._text_field = text_field
        self._mode = mode
        self._axiom_claims = axiom_claims
        self._overfetch = overfetch_factor

    def search(
        self,
        limit: int = 10,
        mode: str | None = None,
        **kwargs: Any,
    ) -> list:
        """Search with post-retrieval verification.

        Accepts all standard ``client.search()`` kwargs.
        Adds ``mode`` override for per-search mode selection.

        Returns:
            List of ScoredPoint objects. In annotate mode, each point's
            payload gains an ``_axiomguard`` key.
        """
        active_mode = mode or self._mode

        fetch_limit = limit
        if active_mode in ("filter", "strict"):
            fetch_limit = int(limit * self._overfetch)

        results = self._client.search(limit=fetch_limit, **kwargs)

        if not results:
            return results

        # Build chunk dicts
        chunks = []
        for point in results:
            payload = point.payload or {}
            chunks.append({
                "text": payload.get(self._text_field, ""),
                "metadata": dict(payload),
                "_point": point,
            })

        # Verify
        verified = verify_chunks(
            chunks,
            kb=self._kb,
            mode=active_mode,
            text_field="text",
            axiom_claims=self._axiom_claims,
        )

        # Truncate
        verified = verified[:limit]

        # Rebuild as ScoredPoint list with updated payloads
        output = []
        for chunk in verified:
            point = chunk["_point"]
            if active_mode == "annotate":
                point.payload["_axiomguard"] = chunk["metadata"].get("_axiomguard", {})
            output.append(point)

        return output

    def __getattr__(self, name: str) -> Any:
        """Delegate all other methods to the underlying client."""
        return getattr(self._client, name)
