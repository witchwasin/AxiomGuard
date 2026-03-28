"""
AxiomGuard Core — Neuro-Symbolic Verification Engine

Architecture:
  1. translate_to_logic()  — LLM-powered NL → Subject-Relation-Object triple
  2. verify()              — Z3 SMT solver proves contradictions mathematically

The LLM backend is pluggable: swap `_llm_backend` for a real API client
(Anthropic, OpenAI, etc.) without changing any verification logic.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable


# =====================================================================
# Data Structures
# =====================================================================


@dataclass
class VerificationResult:
    is_hallucinating: bool
    reason: str


# =====================================================================
# LLM Backend — Pluggable Interface
# =====================================================================


def _mock_llm_translate(text: str) -> dict:
    """Rule-based mock that simulates LLM extraction of SRO triples.

    Handles common sentence patterns to keep the PoC running without
    API calls. Designed to be replaced by a real LLM backend.
    """
    normalized = text.strip().rstrip(".").lower()

    # Pattern: "X is in Y" / "X is located in Y" / "X is based in Y"
    for prep in ["is located in", "is based in", "located in", "based in", "is in"]:
        if prep in normalized:
            parts = normalized.split(prep, 1)
            subject = _extract_subject(parts[0].strip())
            obj = parts[1].strip().title()
            return {"subject": subject, "relation": "location", "object": obj}

    # Pattern: "X is Y" (identity / attribute)
    if " is " in normalized:
        parts = normalized.split(" is ", 1)
        subject = _extract_subject(parts[0].strip())
        obj = parts[1].strip()
        # Preserve original casing from the raw text for the object
        raw_obj = text.strip().rstrip(".").split(" is ", 1)
        if len(raw_obj) == 2:
            obj = raw_obj[1].strip()
        return {"subject": subject, "relation": "identity", "object": obj}

    # Fallback: return the whole text as a single claim
    return {"subject": "unknown", "relation": "states", "object": normalized}


def _extract_subject(raw: str) -> str:
    """Normalize a subject phrase to a canonical entity name."""
    # Strip common determiners
    for prefix in ["the ", "our ", "a ", "an ", "their ", "its "]:
        if raw.startswith(prefix):
            raw = raw[len(prefix):]

    # Map known synonyms to canonical forms
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


# Active backend — reassign this to swap implementations
_llm_backend: Callable[[str], dict] = _mock_llm_translate


def set_llm_backend(backend: Callable[[str], dict]) -> None:
    """Replace the mock LLM with a real API client.

    Args:
        backend: A function that takes a text string and returns a dict
                 with keys "subject", "relation", "object".

    Example:
        from anthropic import Anthropic
        client = Anthropic()

        def my_backend(text: str) -> dict:
            resp = client.messages.create(...)
            return json.loads(resp.content[0].text)

        set_llm_backend(my_backend)
    """
    global _llm_backend
    _llm_backend = backend


# =====================================================================
# Public API — Logic Translation
# =====================================================================


def translate_to_logic(text: str) -> dict:
    """Translate natural language to a Subject-Relation-Object triple.

    Uses the active LLM backend (mock by default) to extract structured
    logic from free-form text.

    Args:
        text: A natural language statement.

    Returns:
        A dict with keys "subject", "relation", "object".

    Example:
        >>> translate_to_logic("The company headquarters is in Chiang Mai.")
        {"subject": "company", "relation": "location", "object": "Chiang Mai"}
    """
    return _llm_backend(text)


# =====================================================================
# Public API — Verification
# =====================================================================


def verify(response: str, axioms: list[str]) -> VerificationResult:
    """Verify an LLM response against a set of ground-truth axioms.

    Pipeline:
      1. Translate each axiom to a Subject-Relation-Object triple (via LLM).
      2. Translate the response to a Subject-Relation-Object triple (via LLM).
      3. Z3 SMT solver: assert all triples with a uniqueness axiom for
         exclusive relations. If UNSAT → proven contradiction → hallucination.

    Args:
        response: The LLM-generated text to verify.
        axioms: Ground-truth statements the response must not contradict.

    Returns:
        VerificationResult indicating whether the response is hallucinating.
    """
    from axiomguard.z3_engine import check_contradiction_z3

    # Step 1: Translate axioms to logic (LLM layer)
    axiom_triples = [translate_to_logic(axiom) for axiom in axioms]

    # Step 2: Translate response to logic (LLM layer)
    response_triple = translate_to_logic(response)

    # Step 3: Z3 formal contradiction check (Math layer)
    is_hallucinating, reason = check_contradiction_z3(axiom_triples, response_triple)

    return VerificationResult(is_hallucinating=is_hallucinating, reason=reason)
