"""
AxiomGuard LlamaIndex Integration — Node postprocessor and query engine wrapper.

Two components:
  1. AxiomGuardPostprocessor — filters/annotates retrieved nodes
  2. AxiomGuardQueryEngine — wraps a query engine with self-correction

Install:
    pip install "axiomguard[llamaindex]"

Usage::

    from axiomguard.integrations.llamaindex import AxiomGuardPostprocessor

    postprocessor = AxiomGuardPostprocessor(
        knowledge_base=kb,
        mode="filter",
    )
    # Use in query engine:
    query_engine = index.as_query_engine(
        node_postprocessors=[postprocessor],
    )
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from axiomguard.knowledge_base import KnowledgeBase
from axiomguard.models import Claim

try:
    from llama_index.core.postprocessor.types import BaseNodePostprocessor
    from llama_index.core.schema import NodeWithScore, QueryBundle

    _HAS_LLAMAINDEX = True
except ImportError:
    _HAS_LLAMAINDEX = False


_PP_VALID_MODES = {"filter", "annotate", "strict"}

# Conditional base: inherit from BaseNodePostprocessor if LlamaIndex available
_PostprocessorBase = BaseNodePostprocessor if _HAS_LLAMAINDEX else object


class AxiomGuardPostprocessor(_PostprocessorBase):
    """Node postprocessor that verifies retrieved nodes against AxiomGuard rules.

    Inherits from LlamaIndex BaseNodePostprocessor when available.

    Modes:
      - "filter": Remove nodes that contain hallucinations.
      - "annotate": Keep all nodes, add verification metadata.
      - "strict": Remove hallucinating nodes, raise if ALL are removed.

    Args:
        knowledge_base: AxiomGuard KnowledgeBase with loaded rules.
        mode: "filter" | "annotate" | "strict" (default: "filter").
    """

    def __init__(
        self,
        knowledge_base: KnowledgeBase,
        mode: str = "filter",
    ):
        if mode not in _PP_VALID_MODES:
            raise ValueError(f"mode must be one of {_PP_VALID_MODES}, got {mode!r}")
        self.kb = knowledge_base
        self.mode = mode

    def postprocess_nodes(
        self,
        nodes: list,
        query_bundle: Any = None,
    ) -> list:
        """Verify and filter/annotate nodes.

        Args:
            nodes: List of NodeWithScore or similar objects with .node.text.
            query_bundle: Optional query context (unused, for API compat).

        Returns:
            Processed list of nodes.
        """
        results = []

        for node_with_score in nodes:
            text = self._extract_text(node_with_score)
            claims = [Claim(subject="node", relation="content", object=text)]
            verification = self.kb.verify(response_claims=claims)

            if self.mode == "filter":
                if not verification.is_hallucinating:
                    results.append(node_with_score)
            elif self.mode == "strict":
                if not verification.is_hallucinating:
                    results.append(node_with_score)
            else:  # annotate
                self._add_metadata(node_with_score, verification)
                results.append(node_with_score)

        if self.mode == "strict" and not results and nodes:
            raise ValueError(
                "AxiomGuard strict mode: all retrieved nodes failed verification. "
                f"Original count: {len(nodes)}"
            )

        return results

    @staticmethod
    def _extract_text(node: Any) -> str:
        """Extract text from various node formats."""
        if hasattr(node, "node") and hasattr(node.node, "text"):
            return node.node.text
        if hasattr(node, "text"):
            return node.text
        if isinstance(node, dict):
            return node.get("text", node.get("content", str(node)))
        return str(node)

    @staticmethod
    def _add_metadata(node: Any, verification: Any) -> None:
        """Add AxiomGuard verification metadata to a node."""
        meta = {
            "is_hallucinating": verification.is_hallucinating,
            "reason": verification.reason,
        }
        if hasattr(node, "node") and hasattr(node.node, "metadata"):
            node.node.metadata["axiomguard"] = meta
        elif hasattr(node, "metadata"):
            node.metadata["axiomguard"] = meta


class AxiomGuardQueryEngine:
    """Query engine wrapper with AxiomGuard self-correction loop.

    Wraps any query engine (or callable) and verifies the response.
    On violation, retries with correction feedback.

    Args:
        base_engine: Object with .query() method, or a callable (str) -> str.
        knowledge_base: AxiomGuard KnowledgeBase with loaded rules.
        max_retries: Maximum correction attempts (default: 2).
    """

    def __init__(
        self,
        base_engine: Any,
        knowledge_base: KnowledgeBase,
        max_retries: int = 2,
    ):
        self.engine = base_engine
        self.kb = knowledge_base
        self.max_retries = max_retries

    def query(self, query_str: str) -> Dict[str, Any]:
        """Query with verification and self-correction.

        Args:
            query_str: The user query.

        Returns:
            Dict with "response", "status", "attempts", "metadata".
        """
        from axiomguard.core import generate_with_guard

        if hasattr(self.engine, "query"):
            def llm_fn(prompt: str) -> str:
                result = self.engine.query(prompt)
                return str(result)
        elif callable(self.engine):
            llm_fn = self.engine
        else:
            raise ValueError("base_engine must have .query() or be callable")

        result = generate_with_guard(
            prompt=query_str,
            kb=self.kb,
            llm_generate=llm_fn,
            max_retries=self.max_retries,
        )

        return {
            "response": result.response,
            "status": result.status,
            "attempts": result.attempts,
            "metadata": {
                "axiomguard": {
                    "status": result.status,
                    "attempts": result.attempts,
                }
            },
        }
