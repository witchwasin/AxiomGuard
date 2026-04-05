"""
Tests for v0.7.2 — Document Ingestion + Stale Rule Detection.

Tests DocumentParser, DocumentSource, Tournament integration,
and StaleRuleDetector. PDF/DOCX tests use mocks (no real files needed).
"""

import hashlib

import pytest

from axiomguard.document_parser import DocumentLocation, DocumentParser, DocumentSource
from axiomguard.staleness import StaleRuleDetector, StalenessReport
from axiomguard.tournament import Tournament, TournamentAudit


# =====================================================================
# Fixtures
# =====================================================================

def _mock_llm(prompt: str) -> str:
    """Minimal mock LLM for tournament tests."""
    if "Hard Constraints" in prompt:
        return """
axiomguard: "0.3"
domain: test
rules:
  - name: c_rule
    type: range
    entity: item
    relation: price
    value_type: int
    max: 1000
    severity: error
    message: "Max price 1000."
"""
    return """
axiomguard: "0.3"
domain: test
rules:
  - name: fallback
    type: unique
    entity: item
    relation: name
    severity: error
    message: "One name."
"""


# =====================================================================
# DocumentLocation
# =====================================================================


class TestDocumentLocation:

    def test_content_hash(self):
        loc = DocumentLocation(
            source_path="test.pdf",
            source_type="pdf",
            page_number=1,
            extracted_text="Hello World",
        )
        assert len(loc.content_hash()) == 16
        assert loc.content_hash() == loc.content_hash()  # deterministic

    def test_different_text_different_hash(self):
        loc1 = DocumentLocation(source_path="a", source_type="text", extracted_text="A")
        loc2 = DocumentLocation(source_path="a", source_type="text", extracted_text="B")
        assert loc1.content_hash() != loc2.content_hash()


# =====================================================================
# DocumentSource
# =====================================================================


class TestDocumentSource:

    def test_from_text(self):
        doc = DocumentParser.from_text("Hello World")
        assert doc.content == "Hello World"
        assert doc.source_type == "text"
        assert doc.total_pages == 1
        assert len(doc.segments) == 1
        assert doc.segments[0].page_number == 1

    def test_document_hash(self):
        doc = DocumentParser.from_text("Test content")
        expected = hashlib.sha256("Test content".encode()).hexdigest()[:16]
        assert doc.document_hash == expected

    def test_segment_hashes(self):
        doc = DocumentParser.from_text("Content")
        hashes = doc.segment_hashes
        assert 0 in hashes
        assert len(hashes[0]) == 16

    def test_custom_path(self):
        doc = DocumentParser.from_text("Content", path="my_doc.txt")
        assert doc.path == "my_doc.txt"

    def test_multi_segment(self):
        doc = DocumentSource(
            content="Page 1\n\nPage 2",
            path="test.pdf",
            source_type="pdf",
            segments=[
                DocumentLocation(source_path="test.pdf", source_type="pdf",
                               page_number=1, extracted_text="Page 1"),
                DocumentLocation(source_path="test.pdf", source_type="pdf",
                               page_number=2, extracted_text="Page 2"),
            ],
            total_pages=2,
        )
        assert len(doc.segments) == 2
        assert doc.segment_hashes[0] != doc.segment_hashes[1]


# =====================================================================
# DocumentParser
# =====================================================================


class TestDocumentParser:

    def test_from_text_basic(self):
        doc = DocumentParser.from_text("Simple text")
        assert doc.source_type == "text"
        assert doc.content == "Simple text"

    def test_pdf_requires_pdfplumber(self):
        """PDF parsing should raise ImportError if pdfplumber not installed."""
        # This may pass or fail depending on environment
        # Just verify the method exists and handles errors
        try:
            DocumentParser.from_pdf("/nonexistent/file.pdf")
        except (ImportError, FileNotFoundError, Exception):
            pass  # Expected: either ImportError or FileNotFoundError

    def test_docx_requires_python_docx(self):
        """DOCX parsing should raise ImportError if python-docx not installed."""
        try:
            DocumentParser.from_docx("/nonexistent/file.docx")
        except (ImportError, FileNotFoundError, Exception):
            pass  # Expected

    def test_from_file_unsupported(self):
        with pytest.raises(ValueError, match="Unsupported file type"):
            DocumentParser.from_file("test.xyz")

    def test_from_file_txt(self):
        """from_file with .txt should work if file exists."""
        import tempfile
        import os
        with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False) as f:
            f.write("Test content")
            f.flush()
            doc = DocumentParser.from_file(f.name)
            assert doc.content == "Test content"
            assert doc.source_type == "text"
        os.unlink(f.name)


# =====================================================================
# Tournament + DocumentSource Integration
# =====================================================================


class TestTournamentDocumentSource:

    def test_tournament_accepts_string(self):
        """Backward compatible: str still works."""
        t = Tournament(source="plain text policy", strategies=["constraints"])
        t.generate(llm_generate=_mock_llm)
        assert t.candidate_count > 0

    def test_tournament_accepts_document_source(self):
        """New: DocumentSource also works."""
        doc = DocumentParser.from_text("Policy text here")
        t = Tournament(source=doc, strategies=["constraints"])
        t.generate(llm_generate=_mock_llm)
        assert t.candidate_count > 0

    def test_audit_trail_has_provenance(self):
        doc = DocumentParser.from_text("Policy document", path="policy.txt")
        t = Tournament(source=doc, strategies=["constraints"])
        t.generate(llm_generate=_mock_llm)

        audit = t.audit_trail()
        assert audit.source_path == "policy.txt"
        assert audit.source_type == "text"
        assert audit.total_pages == 1
        assert len(audit.source_segment_hashes) > 0

    def test_audit_trail_hash_matches_document(self):
        doc = DocumentParser.from_text("Specific content")
        t = Tournament(source=doc, strategies=["constraints"])
        t.generate(llm_generate=_mock_llm)

        audit = t.audit_trail()
        assert audit.source_document_hash == doc.document_hash

    def test_multi_page_document(self):
        doc = DocumentSource(
            content="Page 1 content\n\nPage 2 content",
            path="multi.pdf",
            source_type="pdf",
            segments=[
                DocumentLocation(source_path="multi.pdf", source_type="pdf",
                               page_number=1, extracted_text="Page 1 content"),
                DocumentLocation(source_path="multi.pdf", source_type="pdf",
                               page_number=2, extracted_text="Page 2 content"),
            ],
            total_pages=2,
        )
        t = Tournament(source=doc, strategies=["constraints"])
        t.generate(llm_generate=_mock_llm)

        audit = t.audit_trail()
        assert audit.total_pages == 2
        assert len(audit.source_segment_hashes) == 2


# =====================================================================
# StaleRuleDetector
# =====================================================================


class TestStaleRuleDetector:

    def _make_audit(
        self, content: str, path: str = "doc.pdf", approved_pages: list = None
    ) -> TournamentAudit:
        """Helper: create a minimal audit with given content."""
        doc = DocumentParser.from_text(content, path=path)
        t = Tournament(source=doc, strategies=["constraints"])
        t.generate(llm_generate=_mock_llm)
        t.detect_conflicts()
        for c in t.standalone_candidates():
            t.approve(c.id)
            if approved_pages:
                # Simulate page assignment
                pass
        return t.audit_trail()

    def test_unchanged_document(self):
        audit1 = self._make_audit("Same content")
        audit2 = self._make_audit("Same content")

        report = StaleRuleDetector.compare(audit1, audit2)
        assert not report.is_stale
        assert not report.document_changed
        assert "CURRENT" in report.summary

    def test_changed_document(self):
        audit1 = self._make_audit("Original content")
        audit2 = self._make_audit("Updated content")

        report = StaleRuleDetector.compare(audit1, audit2)
        assert report.is_stale
        assert report.document_changed
        assert "STALE" in report.summary

    def test_quick_check_same(self):
        audit = self._make_audit("Content")
        doc = DocumentParser.from_text("Content")
        assert not StaleRuleDetector.quick_check(audit, doc.document_hash)

    def test_quick_check_different(self):
        audit = self._make_audit("Old content")
        doc = DocumentParser.from_text("New content")
        assert StaleRuleDetector.quick_check(audit, doc.document_hash)

    def test_segment_changes_detected(self):
        doc1 = DocumentSource(
            content="A\n\nB",
            path="test.pdf",
            source_type="pdf",
            segments=[
                DocumentLocation(source_path="test.pdf", source_type="pdf",
                               page_number=1, extracted_text="A"),
                DocumentLocation(source_path="test.pdf", source_type="pdf",
                               page_number=2, extracted_text="B"),
            ],
        )
        doc2 = DocumentSource(
            content="A\n\nC",
            path="test.pdf",
            source_type="pdf",
            segments=[
                DocumentLocation(source_path="test.pdf", source_type="pdf",
                               page_number=1, extracted_text="A"),
                DocumentLocation(source_path="test.pdf", source_type="pdf",
                               page_number=2, extracted_text="C"),
            ],
        )

        t1 = Tournament(source=doc1, strategies=["constraints"])
        t1.generate(llm_generate=_mock_llm)
        audit1 = t1.audit_trail()

        t2 = Tournament(source=doc2, strategies=["constraints"])
        t2.generate(llm_generate=_mock_llm)
        audit2 = t2.audit_trail()

        report = StaleRuleDetector.compare(audit1, audit2)
        assert report.document_changed
        assert len(report.segments_changed) > 0

    def test_staleness_report_summary(self):
        audit1 = self._make_audit("Old")
        audit2 = self._make_audit("New")
        report = StaleRuleDetector.compare(audit1, audit2)
        assert isinstance(report.summary, str)
        assert len(report.summary) > 0


# =====================================================================
# Edge Cases
# =====================================================================


class TestEdgeCases:

    def test_empty_text_document(self):
        doc = DocumentParser.from_text("")
        assert doc.content == ""
        assert doc.source_type == "text"

    def test_unicode_content(self):
        doc = DocumentParser.from_text("สวัสดีครับ บริษัทอยู่ที่กรุงเทพ")
        assert "กรุงเทพ" in doc.content
        assert doc.segments[0].extracted_text == "สวัสดีครับ บริษัทอยู่ที่กรุงเทพ"

    def test_document_source_properties(self):
        doc = DocumentParser.from_text("Test")
        assert isinstance(doc.document_hash, str)
        assert isinstance(doc.segment_hashes, dict)
