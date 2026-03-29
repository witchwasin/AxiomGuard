"""
AxiomGuard Models — Data structures for the verification pipeline.

Claim and ExtractionResult use Pydantic for strict LLM output validation.
VerificationResult is a plain dataclass for engine output.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal, Optional

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
    confidence: float = Field(
        default=1.0,
        ge=0.0,
        le=1.0,
        description="Extraction confidence (0.0-1.0). Low values flag "
        "uncertain extractions for human review before Z3. "
        "1.0 = certain (default), < 0.5 = low confidence.",
    )

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
        reason: Human-readable explanation (uses YAML custom message when available).
        confidence: "proven" when Z3 returns UNSAT (mathematical proof),
                    "uncertain" when extraction had issues.
        extraction_warnings: Transparency log of anything unusual
                             during the extraction/resolution stages.
        contradicted_claims: Indices of claims in the unsat core (if available).
        violated_rules: List of YAML rule metadata dicts that were violated.
                        Each dict has keys: name, type, severity, message.
    """

    is_hallucinating: bool
    reason: str
    confidence: Literal["proven", "uncertain"] = "proven"
    extraction_warnings: list[str] = field(default_factory=list)
    contradicted_claims: list[int] = field(default_factory=list)
    violated_rules: list[dict] = field(default_factory=list)


# =====================================================================
# Self-Correction Loop (v0.5.0)
# =====================================================================


@dataclass
class CorrectionAttempt:
    """Record of a single attempt in the correction loop.

    Attributes:
        attempt_number: 1-based attempt index.
        response: The raw LLM response text for this attempt.
        claims: Extracted claims from the response.
        verification: Z3 verification result.
        correction_prompt: The prompt used to request this attempt.
                           None for attempt 1 (original generation).
    """

    attempt_number: int
    response: str
    claims: list[Claim] = field(default_factory=list)
    verification: Optional[VerificationResult] = None
    correction_prompt: Optional[str] = None


@dataclass
class CorrectionResult:
    """Output of generate_with_guard().

    Attributes:
        status: "verified" (pass on 1st try), "corrected" (fixed on retry),
                "failed" (all retries exhausted), "unverifiable" (no claims extracted),
                "constraint_conflict" (same UNSAT on every attempt — rules may conflict).
        response: The final response text (best available).
        attempts: Total number of attempts made.
        max_attempts: Configured limit (1 + max_retries).
        history: Full attempt log for debugging / transparency.
        final_verification: The last VerificationResult (None if unverifiable).
    """

    status: Literal["verified", "corrected", "failed", "unverifiable", "constraint_conflict", "blocked"]
    response: str
    attempts: int
    max_attempts: int
    history: list[CorrectionAttempt] = field(default_factory=list)
    final_verification: Optional[VerificationResult] = None
