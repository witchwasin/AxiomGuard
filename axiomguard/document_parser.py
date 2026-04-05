"""
AxiomGuard Document Parser — Load PDF/DOCX/text with provenance tracking.

Extracts text from documents while preserving location metadata
(page number, section name) so that Tournament-generated rules
can trace back to their source.

Usage::

    from axiomguard.document_parser import DocumentParser

    doc = DocumentParser.from_pdf("policy.pdf")
    # doc.segments[0].page_number == 1
    # doc.segments[0].extracted_text == "Page 1 content..."

    tourney = Tournament(source=doc)

Install for PDF/DOCX support:
    pip install "axiomguard[ingestion]"
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Literal, Optional


@dataclass
class DocumentLocation:
    """Provenance: where in the source document a piece of text came from."""

    source_path: str
    source_type: Literal["text", "pdf", "docx"]
    page_number: Optional[int] = None
    section_name: Optional[str] = None
    extracted_text: str = ""

    def content_hash(self) -> str:
        """SHA-256 hash of this segment's text."""
        return hashlib.sha256(self.extracted_text.encode()).hexdigest()[:16]


@dataclass
class DocumentSource:
    """Container for source material with metadata and provenance.

    Used as input to Tournament(source=...) for document-based
    rule generation with full traceability.
    """

    content: str
    path: str = "text_input"
    source_type: Literal["text", "pdf", "docx"] = "text"
    segments: List[DocumentLocation] = field(default_factory=list)
    total_pages: Optional[int] = None

    @property
    def document_hash(self) -> str:
        """SHA-256 hash of the full content."""
        return hashlib.sha256(self.content.encode()).hexdigest()[:16]

    @property
    def segment_hashes(self) -> dict[int, str]:
        """Map page/segment index → content hash."""
        return {
            i: seg.content_hash()
            for i, seg in enumerate(self.segments)
        }


class DocumentParser:
    """Parse documents into DocumentSource with provenance metadata.

    Supports: plain text, PDF (via pdfplumber), DOCX (via python-docx).
    """

    @staticmethod
    def from_text(text: str, path: str = "text_input") -> DocumentSource:
        """Wrap plain text as a DocumentSource."""
        segments = [
            DocumentLocation(
                source_path=path,
                source_type="text",
                page_number=1,
                extracted_text=text,
            )
        ]
        return DocumentSource(
            content=text,
            path=path,
            source_type="text",
            segments=segments,
            total_pages=1,
        )

    @staticmethod
    def from_pdf(path: str | Path) -> DocumentSource:
        """Extract text from PDF with per-page provenance.

        Requires: pip install "axiomguard[ingestion]"
        """
        try:
            import pdfplumber
        except ImportError:
            raise ImportError(
                "PDF parsing requires pdfplumber. "
                "Install with: pip install 'axiomguard[ingestion]'"
            )

        path = Path(path)
        segments: List[DocumentLocation] = []
        all_text_parts: List[str] = []

        with pdfplumber.open(path) as pdf:
            for i, page in enumerate(pdf.pages, start=1):
                text = page.extract_text() or ""
                if text.strip():
                    segments.append(
                        DocumentLocation(
                            source_path=str(path),
                            source_type="pdf",
                            page_number=i,
                            extracted_text=text,
                        )
                    )
                    all_text_parts.append(text)

            total_pages = len(pdf.pages)

        full_content = "\n\n".join(all_text_parts)
        return DocumentSource(
            content=full_content,
            path=str(path),
            source_type="pdf",
            segments=segments,
            total_pages=total_pages,
        )

    @staticmethod
    def from_docx(path: str | Path) -> DocumentSource:
        """Extract text from DOCX with section-level provenance.

        Requires: pip install "axiomguard[ingestion]"
        """
        try:
            import docx
        except ImportError:
            raise ImportError(
                "DOCX parsing requires python-docx. "
                "Install with: pip install 'axiomguard[ingestion]'"
            )

        path = Path(path)
        doc = docx.Document(str(path))

        segments: List[DocumentLocation] = []
        current_section = "Document"
        current_text_parts: List[str] = []
        page_counter = 1

        for para in doc.paragraphs:
            # Detect section headings
            if para.style and para.style.name and para.style.name.startswith("Heading"):
                # Flush previous section
                if current_text_parts:
                    segments.append(
                        DocumentLocation(
                            source_path=str(path),
                            source_type="docx",
                            page_number=page_counter,
                            section_name=current_section,
                            extracted_text="\n".join(current_text_parts),
                        )
                    )
                    page_counter += 1
                    current_text_parts = []
                current_section = para.text
            elif para.text.strip():
                current_text_parts.append(para.text)

        # Flush last section
        if current_text_parts:
            segments.append(
                DocumentLocation(
                    source_path=str(path),
                    source_type="docx",
                    page_number=page_counter,
                    section_name=current_section,
                    extracted_text="\n".join(current_text_parts),
                )
            )

        full_content = "\n\n".join(seg.extracted_text for seg in segments)
        return DocumentSource(
            content=full_content,
            path=str(path),
            source_type="docx",
            segments=segments,
            total_pages=len(segments),
        )

    @staticmethod
    def from_file(path: str | Path) -> DocumentSource:
        """Auto-detect file type and parse accordingly."""
        path = Path(path)
        suffix = path.suffix.lower()

        if suffix == ".pdf":
            return DocumentParser.from_pdf(path)
        elif suffix in (".docx", ".doc"):
            return DocumentParser.from_docx(path)
        elif suffix in (".txt", ".md", ".yml", ".yaml"):
            text = path.read_text(encoding="utf-8")
            return DocumentParser.from_text(text, str(path))
        else:
            raise ValueError(
                f"Unsupported file type: {suffix}. "
                f"Supported: .pdf, .docx, .txt, .md, .yml"
            )
