"""
AxiomGuard Models — Data structures for the verification pipeline.

Claim and ExtractionResult use Pydantic for strict LLM output validation.
VerificationResult is a plain dataclass for engine output.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

from pydantic import BaseModel, Field


# =====================================================================
# LLM Extraction Models (Pydantic — validated)
# =====================================================================


class Claim(BaseModel):
    """A single atomic Subject-Relation-Object triple.

    Atomic Proposition Rules (from v020 research):
      1. Single-fact: exactly one relationship per triple.
      2. Non-redundant: no inverse duplicates.
      3. Grounded: subject/object must be concrete entities, not descriptions.
      4. Temporally flat: present-tense assertions only (for v0.2.0).
    """

    subject: str = Field(min_length=1, description="Canonical entity name")
    relation: str = Field(min_length=1, description="Relation type (location, identity, ...)")
    object: str = Field(min_length=1, description="Concrete value or entity")
    negated: bool = Field(default=False, description="True if the claim is a negation")

    def as_key(self) -> tuple[str, str, str]:
        """Normalized dedup key — order-independent for subject/object."""
        s, r, o = self.subject.lower(), self.relation.lower(), self.object.lower()
        return (min(s, o), r, max(s, o))


class ExtractionResult(BaseModel):
    """Multi-claim extraction output from an LLM backend.

    The LLM must return a JSON object with a "claims" array.
    Each claim is validated against the Claim schema.
    """

    claims: list[Claim] = Field(min_length=1)


# =====================================================================
# Verification Output (dataclass — no validation needed)
# =====================================================================


@dataclass
class VerificationResult:
    """Output of the AxiomGuard verification pipeline.

    Attributes:
        is_hallucinating: True if a contradiction was detected.
        reason: Human-readable explanation.
        confidence: "proven" when Z3 returns UNSAT (mathematical proof),
                    "uncertain" when extraction had issues.
        extraction_warnings: Transparency log of anything unusual
                             during the extraction/resolution stages.
        contradicted_claims: Indices of claims in the unsat core (if available).
    """

    is_hallucinating: bool
    reason: str
    confidence: Literal["proven", "uncertain"] = "proven"
    extraction_warnings: list[str] = field(default_factory=list)
    contradicted_claims: list[int] = field(default_factory=list)
