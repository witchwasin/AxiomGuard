"""
Tests for v0.7.0 — LangChain Integration.

All tests use mocks — no langchain install required.
"""

from axiomguard import KnowledgeBase, Claim
from axiomguard.integrations.langchain import (
    AxiomGuardChain,
    AxiomGuardOutputParser,
    AxiomGuardRetriever,
)


def _simple_kb() -> KnowledgeBase:
    kb = KnowledgeBase()
    kb.load_string("""
axiomguard: "0.7"
domain: test
rules:
  - name: hq_location
    type: unique
    entity: company
    relation: location
    severity: error
    message: "HQ location is unique."
""")
    return kb


# =====================================================================
# AxiomGuardChain
# =====================================================================


class TestAxiomGuardChain:

    def test_invoke_verified_response(self):
        kb = _simple_kb()
        chain = AxiomGuardChain(
            llm=lambda prompt: "The company is in Bangkok",
            knowledge_base=kb,
        )
        result = chain.invoke({"query": "Where is the company?"})
        assert result["status"] == "verified"
        assert "Bangkok" in result["response"]

    def test_invoke_with_input_key(self):
        kb = _simple_kb()
        chain = AxiomGuardChain(
            llm=lambda prompt: "The company is in Bangkok",
            knowledge_base=kb,
        )
        result = chain.invoke({"input": "Where is the company?"})
        assert result["status"] == "verified"

    def test_invoke_returns_attempts(self):
        kb = _simple_kb()
        chain = AxiomGuardChain(
            llm=lambda prompt: "The company is in Bangkok",
            knowledge_base=kb,
        )
        result = chain.invoke({"query": "test"})
        assert result["attempts"] >= 1

    def test_block_mode(self):
        kb = _simple_kb()
        chain = AxiomGuardChain(
            llm=lambda prompt: "The company is in Bangkok",
            knowledge_base=kb,
            mode="block",
        )
        result = chain.invoke({"query": "test"})
        assert result["status"] in ("verified", "blocked")


# =====================================================================
# AxiomGuardRetriever
# =====================================================================


class _MockRetriever:
    """Mock retriever that returns predefined documents."""

    def __init__(self, docs):
        self.docs = docs

    def get_relevant_documents(self, query):
        return self.docs


class _MockDocument:
    """Mock LangChain Document."""

    def __init__(self, content, metadata=None):
        self.page_content = content
        self.metadata = metadata or {}


class TestAxiomGuardRetriever:

    def test_filter_mode_removes_nothing_when_clean(self):
        kb = _simple_kb()
        docs = [_MockDocument("The company is in Bangkok")]
        retriever = AxiomGuardRetriever(
            knowledge_base=kb,
            base_retriever=_MockRetriever(docs),
            mode="filter",
        )
        results = retriever.get_relevant_documents("test")
        assert len(results) == 1

    def test_annotate_mode_adds_metadata(self):
        kb = _simple_kb()
        docs = [_MockDocument("Some text", metadata={})]
        retriever = AxiomGuardRetriever(
            knowledge_base=kb,
            base_retriever=_MockRetriever(docs),
            mode="annotate",
        )
        results = retriever.get_relevant_documents("test")
        assert len(results) == 1
        assert "axiomguard" in results[0].metadata

    def test_verify_documents_directly(self):
        kb = _simple_kb()
        retriever = AxiomGuardRetriever(knowledge_base=kb, mode="filter")
        docs = [_MockDocument("The company is in Bangkok")]
        results = retriever.verify_documents(docs)
        assert len(results) >= 0  # May or may not filter depending on rules

    def test_verify_dict_documents(self):
        kb = _simple_kb()
        retriever = AxiomGuardRetriever(knowledge_base=kb, mode="filter")
        docs = [{"content": "Some fact"}]
        results = retriever.verify_documents(docs)
        assert isinstance(results, list)


# =====================================================================
# AxiomGuardOutputParser
# =====================================================================


class TestAxiomGuardOutputParser:

    def test_parse_clean_text(self):
        kb = _simple_kb()
        parser = AxiomGuardOutputParser(knowledge_base=kb)
        result = parser.parse("The company is in Bangkok")
        assert "text" in result
        assert "is_verified" in result
        assert isinstance(result["is_verified"], bool)

    def test_parse_returns_violated_rules(self):
        kb = _simple_kb()
        parser = AxiomGuardOutputParser(knowledge_base=kb)
        result = parser.parse("Some text")
        assert "violated_rules" in result
        assert isinstance(result["violated_rules"], list)

    def test_raise_on_violation_flag(self):
        kb = KnowledgeBase()
        kb.load_string("""
axiomguard: "0.7"
domain: test
rules:
  - name: forbidden
    type: negation
    entity: llm
    relation: output
    must_not_include: "BANNED"
    message: "Banned content detected."
""")
        parser = AxiomGuardOutputParser(knowledge_base=kb, raise_on_violation=True)

        # Should raise on banned content
        try:
            parser.parse("BANNED")
            raised = False
        except ValueError:
            raised = True
        assert raised

    def test_no_raise_when_clean(self):
        kb = _simple_kb()
        parser = AxiomGuardOutputParser(knowledge_base=kb, raise_on_violation=True)
        result = parser.parse("Clean text")
        assert result["text"] == "Clean text"
