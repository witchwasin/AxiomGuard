"""
AxiomGuard LangChain Integration — Drop-in components for LangChain RAG pipelines.

Three components:
  1. AxiomGuardChain — Runnable that wraps generate_with_guard()
  2. AxiomGuardRetriever — BaseRetriever that filters chunks via verify_chunks()
  3. AxiomGuardOutputParser — Verifies parsed output against rules

Install:
    pip install "axiomguard[langchain]"

Usage::

    from axiomguard.integrations.langchain import AxiomGuardChain

    chain = AxiomGuardChain(
        llm=my_llm,
        knowledge_base=kb,
        max_retries=2,
    )
    result = chain.invoke({"query": "What is the company policy?"})
"""

from __future__ import annotations

from typing import Any, Callable, Dict, List, Optional

from axiomguard.knowledge_base import KnowledgeBase
from axiomguard.models import Claim, VerificationResult

try:
    from langchain_core.callbacks import CallbackManagerForChainRun
    from langchain_core.documents import Document
    from langchain_core.language_models import BaseLanguageModel
    from langchain_core.output_parsers import StrOutputParser
    from langchain_core.retrievers import BaseRetriever
    from langchain_core.runnables import Runnable, RunnableConfig

    _HAS_LANGCHAIN = True
except ImportError:
    _HAS_LANGCHAIN = False


def _require_langchain() -> None:
    if not _HAS_LANGCHAIN:
        raise ImportError(
            "LangChain integration requires langchain-core. "
            "Install with: pip install 'axiomguard[langchain]'"
        )


_CHAIN_VALID_MODES = {"correct", "block", "escalate"}


# Conditional base: inherit from Runnable if LangChain is available
_ChainBase = Runnable if _HAS_LANGCHAIN else object


class AxiomGuardChain(_ChainBase):
    """LangChain-compatible chain that wraps generate_with_guard().

    Inherits from LangChain Runnable when available for LCEL compatibility.

    Args:
        llm: Any callable (str) -> str, or LangChain BaseLanguageModel.
        knowledge_base: AxiomGuard KnowledgeBase with loaded rules.
        max_retries: Maximum correction attempts (default: 2).
        mode: "correct" | "block" | "escalate" (default: "correct").
    """

    def __init__(
        self,
        llm: Any,
        knowledge_base: KnowledgeBase,
        max_retries: int = 2,
        mode: str = "correct",
    ):
        if mode not in _CHAIN_VALID_MODES:
            raise ValueError(f"mode must be one of {_CHAIN_VALID_MODES}, got {mode!r}")
        self.llm = llm
        self.kb = knowledge_base
        self.max_retries = max_retries
        self.mode = mode

    def invoke(self, input: Dict[str, Any], **kwargs: Any) -> Dict[str, Any]:
        """Run the chain: generate → verify → correct if needed.

        Args:
            input: Dict with "query" key.

        Returns:
            Dict with "response", "status", "attempts", "violated_rules".
        """
        from axiomguard.core import generate_with_guard

        query = input.get("query", input.get("input", ""))

        # Normalize LLM to callable
        if _HAS_LANGCHAIN and isinstance(self.llm, BaseLanguageModel):
            def llm_fn(prompt: str) -> str:
                return self.llm.invoke(prompt).content
        elif callable(self.llm):
            llm_fn = self.llm
        else:
            raise ValueError("llm must be callable or a LangChain BaseLanguageModel")

        result = generate_with_guard(
            prompt=query,
            kb=self.kb,
            llm_generate=llm_fn,
            max_retries=self.max_retries,
            mode=self.mode,
        )

        return {
            "response": result.response,
            "status": result.status,
            "attempts": result.attempts,
            "violated_rules": [
                a.verification.violated_rules
                for a in result.history
                if a.verification and a.verification.violated_rules
            ],
        }


class AxiomGuardRetriever:
    """Retriever wrapper that filters documents through AxiomGuard verification.

    Wraps a base retriever (or list of Documents) and verifies each chunk
    against the KnowledgeBase. Only verified (non-hallucinating) chunks
    are returned.

    Args:
        base_retriever: A retriever with a get_relevant_documents() method,
                       or None if using verify_documents() directly.
        knowledge_base: AxiomGuard KnowledgeBase with loaded rules.
        mode: "filter" removes bad chunks, "annotate" keeps all with metadata.
    """

    def __init__(
        self,
        knowledge_base: KnowledgeBase,
        base_retriever: Any = None,
        mode: str = "filter",
    ):
        self.kb = knowledge_base
        self.base_retriever = base_retriever
        self.mode = mode

    def get_relevant_documents(self, query: str) -> list:
        """Retrieve and verify documents.

        Args:
            query: The search query.

        Returns:
            List of verified Document objects.
        """
        if self.base_retriever is None:
            raise ValueError("base_retriever is required for get_relevant_documents()")

        docs = self.base_retriever.get_relevant_documents(query)
        return self.verify_documents(docs)

    def verify_documents(self, documents: list) -> list:
        """Verify a list of documents against the KnowledgeBase.

        Args:
            documents: List of objects with .page_content attribute (or dicts with "content").

        Returns:
            Filtered or annotated list depending on mode.
        """
        results = []
        for doc in documents:
            content = getattr(doc, "page_content", None)
            if content is None:
                content = doc.get("content", "") if isinstance(doc, dict) else str(doc)

            claims = [
                Claim(subject="document", relation="content", object=content)
            ]
            verification = self.kb.verify(response_claims=claims)

            if self.mode == "filter":
                if not verification.is_hallucinating:
                    results.append(doc)
            else:  # annotate
                if hasattr(doc, "metadata"):
                    doc.metadata["axiomguard"] = {
                        "is_hallucinating": verification.is_hallucinating,
                        "reason": verification.reason,
                    }
                results.append(doc)

        return results


class AxiomGuardOutputParser:
    """Output parser that verifies LLM output against AxiomGuard rules.

    Use as a final step in a chain to validate the response.

    Args:
        knowledge_base: AxiomGuard KnowledgeBase with loaded rules.
        raise_on_violation: If True, raises ValueError on hallucination.
    """

    def __init__(
        self,
        knowledge_base: KnowledgeBase,
        raise_on_violation: bool = False,
    ):
        self.kb = knowledge_base
        self.raise_on_violation = raise_on_violation

    def parse(self, text: str) -> Dict[str, Any]:
        """Parse and verify LLM output.

        Args:
            text: Raw LLM output string.

        Returns:
            Dict with "text", "is_verified", "violated_rules".
        """
        claims = [Claim(subject="llm", relation="output", object=text)]
        result = self.kb.verify(response_claims=claims)

        if result.is_hallucinating and self.raise_on_violation:
            rules = [v["message"] for v in result.violated_rules if v.get("message")]
            raise ValueError(
                f"AxiomGuard verification failed: {'; '.join(rules) or result.reason}"
            )

        return {
            "text": text,
            "is_verified": not result.is_hallucinating,
            "violated_rules": result.violated_rules,
            "reason": result.reason,
        }
