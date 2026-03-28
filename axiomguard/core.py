"""
AxiomGuard Core — Neuro-Symbolic Verification Engine

v0.2.0 Pipeline:
  1. Extract claims from text (LLM backend → validation pipeline)
  2. Resolve entities (EntityResolver — deterministic canonicalization)
  3. Prove contradictions (Z3 SMT solver with Assumptions API)

The LLM backend is pluggable: swap via set_llm_backend() for real API clients.
"""

from __future__ import annotations

from typing import Callable, List, Tuple

from axiomguard.models import Claim, VerificationResult
from axiomguard.resolver import EntityResolver


# =====================================================================
# Module-level state
# =====================================================================

_entity_resolver = EntityResolver()


# =====================================================================
# LLM Backend — Pluggable Interface (v0.2.0: returns list[Claim])
# =====================================================================


def _mock_llm_extract(text: str) -> list[Claim]:
    """Rule-based mock that simulates LLM multi-claim extraction.

    Handles common sentence patterns to keep the PoC running without
    API calls. Designed to be replaced by a real LLM backend.
    """
    normalized = text.strip().rstrip(".").lower()

    # Detect negation
    negated = False
    for neg in ["is not ", "isn't ", "not the ", "never "]:
        if neg in normalized:
            negated = True
            normalized = normalized.replace(neg, "is " if "is not " in neg or "isn't " in neg else "")
            break

    # Pattern: "X is in Y" / "X is located in Y" / "X is based in Y"
    for prep in ["is located in", "is based in", "located in", "based in", "is in"]:
        if prep in normalized:
            parts = normalized.split(prep, 1)
            subject = _extract_subject(parts[0].strip())
            obj = parts[1].strip().title()
            return [Claim(subject=subject, relation="location", object=obj, negated=negated)]

    # Pattern: "X is Y" (identity / attribute)
    if " is " in normalized:
        parts = normalized.split(" is ", 1)
        subject = _extract_subject(parts[0].strip())
        obj = parts[1].strip()
        # Preserve original casing from the raw text for the object
        raw_obj = text.strip().rstrip(".").split(" is ", 1)
        if len(raw_obj) == 2:
            obj_original = raw_obj[1].strip()
            # Remove negation words from the preserved casing version
            for neg in ["not ", "NOT ", "Not "]:
                obj_original = obj_original.replace(neg, "")
            obj = obj_original.strip()
        return [Claim(subject=subject, relation="identity", object=obj, negated=negated)]

    # Fallback
    return [Claim(subject="unknown", relation="states", object=normalized)]


def _extract_subject(raw: str) -> str:
    """Normalize a subject phrase to a canonical entity name."""
    for prefix in ["the ", "our ", "a ", "an ", "their ", "its "]:
        if raw.startswith(prefix):
            raw = raw[len(prefix):]

    synonyms = {
        "headquarters": "company",
        "hq": "company",
        "head office": "company",
        "main office": "company",
        "company headquarters": "company",
        "firm": "company",
        "organization": "company",
        "office": "company",
    }
    return synonyms.get(raw, raw)


# Active backend
_llm_backend: Callable[[str], list[Claim]] = _mock_llm_extract


def set_llm_backend(backend: Callable) -> None:
    """Replace the mock LLM with a real API client.

    The backend should be a function that takes a text string and returns
    a list[Claim]. For backward compatibility, backends returning a single
    dict with "subject"/"relation"/"object" keys are auto-wrapped.

    Example::

        from axiomguard.backends.anthropic_llm import create_anthropic_extractor
        set_llm_backend(create_anthropic_extractor())
    """
    global _llm_backend
    _llm_backend = backend


def set_entity_resolver(resolver: EntityResolver) -> None:
    """Replace the default EntityResolver with a custom one.

    Example::

        resolver = EntityResolver(aliases={"กทม": "Bangkok", "สยาม": "Thailand"})
        set_entity_resolver(resolver)
    """
    global _entity_resolver
    _entity_resolver = resolver


# =====================================================================
# Internal — Extraction with backward-compat wrapping
# =====================================================================


def _extract(text: str) -> list[Claim]:
    """Call the active backend and normalize the result to list[Claim].

    Handles v0.1.0 backends that return a single dict.
    """
    result = _llm_backend(text)

    # v0.1.0 compat: single dict → wrap in list[Claim]
    if isinstance(result, dict):
        return [Claim(
            subject=result["subject"],
            relation=result["relation"],
            object=result["object"],
            negated=result.get("negated", False),
        )]

    return result


# =====================================================================
# Public API — Logic Translation
# =====================================================================


def translate_to_logic(text: str) -> dict:
    """Translate natural language to a Subject-Relation-Object triple.

    v0.1.0 compatibility: returns the FIRST extracted claim as a dict.
    For multi-claim extraction, use extract_claims() instead.
    """
    claims = _extract(text)
    c = claims[0]
    return {"subject": c.subject, "relation": c.relation, "object": c.object}


def extract_claims(text: str) -> list[Claim]:
    """Extract all claims from natural language text (v0.2.0).

    Uses the active LLM backend to extract structured claims,
    then resolves entities via the active EntityResolver.

    Args:
        text: A natural language statement.

    Returns:
        A list of resolved Claim objects.
    """
    claims = _extract(text)
    resolved, _ = _entity_resolver.resolve_claims(claims)
    return resolved


# =====================================================================
# Public API — Verification
# =====================================================================


def verify(response: str, axioms: list[str]) -> VerificationResult:
    """Verify an LLM response against a set of ground-truth axioms.

    v0.2.0 Pipeline:
      1. Extract claims from each axiom and the response (LLM layer).
      2. Resolve entities (EntityResolver — deterministic).
      3. Z3 SMT solver with Assumptions API (Math layer).
      4. Return result with confidence level and transparency warnings.

    Args:
        response: The LLM-generated text to verify.
        axioms: Ground-truth statements the response must not contradict.

    Returns:
        VerificationResult with confidence ("proven" or "uncertain")
        and extraction_warnings for full transparency.
    """
    from axiomguard.z3_engine import check_claims

    all_warnings: list[str] = []

    # Step 1: Extract claims from axioms
    axiom_claims: list[Claim] = []
    for axiom in axioms:
        claims = _extract(axiom)
        resolved, warnings = _entity_resolver.resolve_claims(claims)
        axiom_claims.extend(resolved)
        all_warnings.extend(warnings)

    # Step 2: Extract claims from response
    response_claims = _extract(response)
    response_claims, warnings = _entity_resolver.resolve_claims(response_claims)
    all_warnings.extend(warnings)

    # Step 3: Z3 formal contradiction check
    is_hallucinating, reason, contradicted = check_claims(
        axiom_claims, response_claims
    )

    # Step 4: Determine confidence
    # Z3 UNSAT = mathematical proof → always "proven"
    # Z3 SAT/unknown with warnings → "uncertain"
    if is_hallucinating:
        confidence = "proven"  # UNSAT is a proof, period
    elif all_warnings:
        confidence = "uncertain"  # SAT but extraction had issues
    else:
        confidence = "proven"  # SAT with clean extraction

    return VerificationResult(
        is_hallucinating=is_hallucinating,
        reason=reason,
        confidence=confidence,
        extraction_warnings=all_warnings,
        contradicted_claims=contradicted,
    )
