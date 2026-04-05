"""
AxiomGuard Staleness Detector — Detect when rules become outdated.

When source documents are updated, rules derived from those documents
may become stale. This module compares tournament audits to identify
which rules need re-verification.

Usage::

    from axiomguard.staleness import StaleRuleDetector

    old_audit = tournament_v1.audit_trail()
    new_audit = tournament_v2.audit_trail()

    report = StaleRuleDetector.compare(old_audit, new_audit)
    # report.changed_segments → {0: "abc123", 2: "def456"}
    # report.stale_candidates → [CandidateRule(...), ...]
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Set

from axiomguard.tournament import CandidateRule, TournamentAudit


@dataclass
class StalenessReport:
    """Result of comparing two tournament audits."""

    document_changed: bool
    document_path: str = ""
    old_hash: str = ""
    new_hash: str = ""
    segments_changed: Dict[str, str] = field(default_factory=dict)
    segments_added: Set[str] = field(default_factory=set)
    segments_removed: Set[str] = field(default_factory=set)
    stale_candidates: List[CandidateRule] = field(default_factory=list)

    @property
    def is_stale(self) -> bool:
        """True if any part of the source document changed."""
        return self.document_changed

    @property
    def summary(self) -> str:
        """Human-readable summary of staleness status."""
        if not self.document_changed:
            return "CURRENT: Source document unchanged."

        parts = [f"STALE: Source document '{self.document_path}' has changed."]
        if self.segments_changed:
            parts.append(f"  Changed segments: {len(self.segments_changed)}")
        if self.segments_added:
            parts.append(f"  New segments: {len(self.segments_added)}")
        if self.segments_removed:
            parts.append(f"  Removed segments: {len(self.segments_removed)}")
        if self.stale_candidates:
            parts.append(f"  Potentially stale rules: {len(self.stale_candidates)}")
        return "\n".join(parts)


class StaleRuleDetector:
    """Compare tournament audits to detect stale rules."""

    @staticmethod
    def compare(
        old_audit: TournamentAudit,
        new_audit: TournamentAudit,
    ) -> StalenessReport:
        """Compare two audits and identify what changed.

        Args:
            old_audit: The previous tournament audit.
            new_audit: The audit from re-running tournament on updated document.

        Returns:
            StalenessReport with changed segments and stale candidates.
        """
        doc_changed = old_audit.source_document_hash != new_audit.source_document_hash

        old_segs = old_audit.source_segment_hashes
        new_segs = new_audit.source_segment_hashes

        # Find changed segments (same key, different hash)
        changed = {
            k: new_segs[k]
            for k in old_segs
            if k in new_segs and old_segs[k] != new_segs[k]
        }

        # Find added/removed segments
        added = set(new_segs.keys()) - set(old_segs.keys())
        removed = set(old_segs.keys()) - set(new_segs.keys())

        # Identify stale candidates (from changed or removed pages)
        stale_page_indices = set()
        for seg_key in list(changed.keys()) + list(removed):
            try:
                stale_page_indices.add(int(seg_key))
            except ValueError:
                pass

        stale_candidates = []
        for candidate in old_audit.candidates:
            if candidate.status != "approved":
                continue
            if candidate.source_page is not None and candidate.source_page - 1 in stale_page_indices:
                stale_candidates.append(candidate)

        return StalenessReport(
            document_changed=doc_changed,
            document_path=old_audit.source_path,
            old_hash=old_audit.source_document_hash,
            new_hash=new_audit.source_document_hash,
            segments_changed=changed,
            segments_added=added,
            segments_removed=removed,
            stale_candidates=stale_candidates,
        )

    @staticmethod
    def quick_check(
        old_audit: TournamentAudit,
        new_document_hash: str,
    ) -> bool:
        """Quick check: did the document change at all?

        Args:
            old_audit: Previous tournament audit.
            new_document_hash: SHA-256 hash of the current document.

        Returns:
            True if document changed (rules may be stale).
        """
        return old_audit.source_document_hash != new_document_hash
