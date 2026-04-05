"""
Tests for v0.7.0 — LlamaIndex Integration.

All tests use mocks — no llama-index install required.
"""

import pytest

from axiomguard import KnowledgeBase
from axiomguard.integrations.llamaindex import (
    AxiomGuardPostprocessor,
    AxiomGuardQueryEngine,
)


def _simple_kb() -> KnowledgeBase:
    kb = KnowledgeBase()
    kb.load_string("""
axiomguard: "0.7"
domain: test
rules:
  - name: hq
    type: unique
    entity: company
    relation: location
    severity: error
    message: "HQ location is unique."
""")
    return kb


class _MockNode:
    """Mock LlamaIndex node."""
    def __init__(self, text, metadata=None):
        self.text = text
        self.metadata = metadata or {}


class _MockNodeWithScore:
    """Mock LlamaIndex NodeWithScore."""
    def __init__(self, text, score=1.0, metadata=None):
        self.node = _MockNode(text, metadata)
        self.score = score


class _MockQueryEngine:
    """Mock LlamaIndex query engine."""
    def __init__(self, response="The company is in Bangkok"):
        self._response = response

    def query(self, query_str):
        return self._response


# =====================================================================
# AxiomGuardPostprocessor
# =====================================================================


class TestPostprocessor:

    def test_filter_keeps_clean_nodes(self):
        kb = _simple_kb()
        pp = AxiomGuardPostprocessor(knowledge_base=kb, mode="filter")
        nodes = [_MockNodeWithScore("The company is in Bangkok")]
        results = pp.postprocess_nodes(nodes)
        assert len(results) == 1

    def test_annotate_adds_metadata(self):
        kb = _simple_kb()
        pp = AxiomGuardPostprocessor(knowledge_base=kb, mode="annotate")
        nodes = [_MockNodeWithScore("Some fact", metadata={})]
        results = pp.postprocess_nodes(nodes)
        assert len(results) == 1
        assert "axiomguard" in results[0].node.metadata

    def test_strict_mode_raises_when_all_fail(self):
        kb = KnowledgeBase()
        kb.load_string("""
axiomguard: "0.7"
domain: test
rules:
  - name: no_banned
    type: negation
    entity: node
    relation: content
    must_not_include: "BANNED"
    message: "Banned content."
""")
        pp = AxiomGuardPostprocessor(knowledge_base=kb, mode="strict")
        nodes = [_MockNodeWithScore("BANNED")]
        with pytest.raises(ValueError, match="strict mode"):
            pp.postprocess_nodes(nodes)

    def test_empty_nodes_returns_empty(self):
        kb = _simple_kb()
        pp = AxiomGuardPostprocessor(knowledge_base=kb, mode="filter")
        assert pp.postprocess_nodes([]) == []

    def test_dict_nodes(self):
        kb = _simple_kb()
        pp = AxiomGuardPostprocessor(knowledge_base=kb, mode="filter")
        nodes = [{"text": "Some content"}]
        results = pp.postprocess_nodes(nodes)
        assert isinstance(results, list)

    def test_extract_text_from_node_with_score(self):
        text = AxiomGuardPostprocessor._extract_text(
            _MockNodeWithScore("hello")
        )
        assert text == "hello"

    def test_extract_text_from_dict(self):
        text = AxiomGuardPostprocessor._extract_text(
            {"content": "world"}
        )
        assert text == "world"


# =====================================================================
# AxiomGuardQueryEngine
# =====================================================================


class TestQueryEngine:

    def test_query_verified(self):
        kb = _simple_kb()
        engine = AxiomGuardQueryEngine(
            base_engine=_MockQueryEngine(),
            knowledge_base=kb,
        )
        result = engine.query("Where is the company?")
        assert result["status"] == "verified"
        assert "Bangkok" in result["response"]

    def test_query_with_callable(self):
        kb = _simple_kb()
        engine = AxiomGuardQueryEngine(
            base_engine=lambda prompt: "The company is in Bangkok",
            knowledge_base=kb,
        )
        result = engine.query("test")
        assert result["status"] == "verified"

    def test_query_returns_metadata(self):
        kb = _simple_kb()
        engine = AxiomGuardQueryEngine(
            base_engine=_MockQueryEngine(),
            knowledge_base=kb,
        )
        result = engine.query("test")
        assert "metadata" in result
        assert "axiomguard" in result["metadata"]

    def test_query_attempts_tracked(self):
        kb = _simple_kb()
        engine = AxiomGuardQueryEngine(
            base_engine=_MockQueryEngine(),
            knowledge_base=kb,
        )
        result = engine.query("test")
        assert result["attempts"] >= 1
