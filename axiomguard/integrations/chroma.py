"""
AxiomGuard × Chroma — Drop-in verified collection wrapper.

Usage:
    import chromadb
    from axiomguard import KnowledgeBase
    from axiomguard.integrations.chroma import VerifiedCollection

    client = chromadb.Client()
    collection = client.get_or_create_collection("docs")

    kb = KnowledgeBase()
    kb.load("rules/medical.axiom.yml")

    verified = VerifiedCollection(collection, kb=kb)
    results = verified.query(query_texts=["What drug treats X?"], n_results=5)
    # Results are verified — contradictory chunks annotated or filtered

Requires:
    pip install axiomguard[chroma]
"""

from __future__ import annotations

from typing import Any, Literal, Optional

from axiomguard.integration import verify_chunks
from axiomguard.knowledge_base import KnowledgeBase
from axiomguard.models import Claim


class VerifiedCollection:
    """Drop-in wrapper around a Chroma Collection with AxiomGuard verification.

    Delegates all methods to the underlying collection. The ``query()`` method
    adds a post-retrieval verification step that annotates or filters results.

    Args:
        collection: A ``chromadb.Collection`` instance.
        kb: A loaded ``KnowledgeBase`` with compiled YAML rules.
        mode: Verification mode (default: "annotate").
        axiom_claims: Optional ground-truth facts for every query.
        overfetch_factor: Retrieve this many times ``n_results`` to compensate
                          for filtered chunks (default: 2.0 for filter/strict).
    """

    def __init__(
        self,
        collection: Any,
        kb: KnowledgeBase,
        mode: Literal["annotate", "filter", "strict"] = "annotate",
        axiom_claims: list[Claim] | None = None,
        overfetch_factor: float = 2.0,
    ) -> None:
        self._collection = collection
        self._kb = kb
        self._mode = mode
        self._axiom_claims = axiom_claims
        self._overfetch = overfetch_factor

    def query(
        self,
        n_results: int = 10,
        mode: str | None = None,
        **kwargs: Any,
    ) -> dict:
        """Query with post-retrieval verification.

        Accepts all standard ``collection.query()`` kwargs.
        Adds ``mode`` override for per-query mode selection.

        Returns:
            Chroma results dict with verified entries. In annotate mode,
            each metadata dict gains an ``_axiomguard`` key.
        """
        active_mode = mode or self._mode

        # Overfetch when filtering to ensure enough results survive
        fetch_n = n_results
        if active_mode in ("filter", "strict"):
            fetch_n = int(n_results * self._overfetch)

        raw = self._collection.query(n_results=fetch_n, **kwargs)

        # Chroma returns nested lists: results["documents"][0], etc.
        if not raw.get("documents") or not raw["documents"][0]:
            return raw

        docs = raw["documents"][0]
        metas = raw.get("metadatas", [[]])[0]
        ids = raw.get("ids", [[]])[0]
        distances = raw.get("distances", [[]])[0]

        # Build chunk dicts for verify_chunks
        chunks = []
        for i, doc in enumerate(docs):
            chunks.append({
                "text": doc,
                "metadata": dict(metas[i]) if i < len(metas) and metas[i] else {},
                "_id": ids[i] if i < len(ids) else None,
                "_distance": distances[i] if i < len(distances) else None,
            })

        # Verify
        verified = verify_chunks(
            chunks,
            kb=self._kb,
            mode=active_mode,
            text_field="text",
            axiom_claims=self._axiom_claims,
        )

        # Truncate to requested n_results
        verified = verified[:n_results]

        # Rebuild Chroma results shape
        return {
            "ids": [[c["_id"] for c in verified]],
            "documents": [[c["text"] for c in verified]],
            "metadatas": [[c["metadata"] for c in verified]],
            "distances": [[c["_distance"] for c in verified]],
        }

    def __getattr__(self, name: str) -> Any:
        """Delegate all other methods to the underlying collection."""
        return getattr(self._collection, name)
