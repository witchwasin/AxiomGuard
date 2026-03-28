"""
AxiomGuard v0.5.0 — Self-Correction Loop Integration Tests

Tests generate_with_guard() using controllable mock LLMs:
  1. Pass on first attempt (status="verified")
  2. Fail first, pass second (status="corrected")
  3. Fail all attempts (status="failed")
  4. Constraint conflict detection (same UNSAT every attempt)
  5. Unverifiable response (no claims extracted)
  6. Correction prompt is passed to LLM on retry
  7. History tracking (full attempt log)
  8. Timeout handling
  9. Backward compatibility

Run:
    python tests/test_v050_core_loop.py
"""

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from axiomguard import (
    Claim,
    CorrectionResult,
    KnowledgeBase,
    generate_with_guard,
)


# =====================================================================
# Test harness
# =====================================================================

_passed = 0
_total = 0


def _check(name, condition, detail=""):
    global _passed, _total
    _total += 1
    s = "PASS" if condition else "FAIL"
    print(f"  [{s}] {name}")
    if detail:
        print(f"         {detail}")
    if condition:
        _passed += 1


# =====================================================================
# Mock LLM Factories
# =====================================================================

def make_fixed_llm(response: str):
    """LLM that always returns the same response."""
    def llm(prompt: str) -> str:
        return response
    return llm


def make_sequence_llm(responses: list):
    """LLM that returns responses in order. Loops last one if exhausted."""
    call_count = [0]
    def llm(prompt: str) -> str:
        idx = min(call_count[0], len(responses) - 1)
        call_count[0] += 1
        return responses[idx]
    return llm


def make_tracking_llm(responses: list):
    """LLM that tracks prompts received and returns responses in order."""
    prompts_received = []
    call_count = [0]
    def llm(prompt: str) -> str:
        prompts_received.append(prompt)
        idx = min(call_count[0], len(responses) - 1)
        call_count[0] += 1
        return responses[idx]
    llm.prompts = prompts_received
    return llm


# =====================================================================
# Shared KB
# =====================================================================

def make_medical_kb():
    kb = KnowledgeBase()
    kb.load_string("""\
axiomguard: "0.3"
domain: healthcare
rules:
  - name: Warfarin-Aspirin interaction
    type: exclusion
    entity: patient
    relation: takes
    values: [Warfarin, Aspirin]
    severity: error
    message: "CRITICAL: Warfarin + Aspirin = bleeding risk."

  - name: One blood type
    type: unique
    entity: patient
    relation: blood_type
    severity: error
    message: "Patient cannot have two blood types."
""")
    return kb


def make_location_kb():
    kb = KnowledgeBase()
    kb.load_string("""\
axiomguard: "0.3"
domain: test
rules:
  - name: One location
    type: unique
    entity: company
    relation: location
    message: "Company can only have one location."
""")
    return kb


# =====================================================================
# 1. VERIFIED — Pass on first attempt
# =====================================================================

def test_verified_first_attempt():
    print()
    print("-" * 64)
    print("  1. VERIFIED — Pass on First Attempt")
    print("-" * 64)

    kb = make_location_kb()
    axioms = [Claim(subject="company", relation="location", object="Bangkok")]

    # LLM says Bangkok — matches axiom, no contradiction
    llm = make_fixed_llm("The company is in Bangkok")

    result = generate_with_guard(
        prompt="Where is the company?",
        kb=kb,
        llm_generate=llm,
        axiom_claims=axioms,
    )

    _check("status = verified", result.status == "verified")
    _check("attempts = 1", result.attempts == 1)
    _check("response contains Bangkok", "Bangkok" in result.response)
    _check("history has 1 entry", len(result.history) == 1)
    _check("history[0].correction_prompt is None",
         result.history[0].correction_prompt is None)
    _check("final_verification.is_hallucinating = False",
         result.final_verification is not None and not result.final_verification.is_hallucinating)


# =====================================================================
# 2. CORRECTED — Fail first, pass second
# =====================================================================

def test_corrected_second_attempt():
    print()
    print("-" * 64)
    print("  2. CORRECTED — Fail First, Pass Second")
    print("-" * 64)

    kb = make_location_kb()
    axioms = [Claim(subject="company", relation="location", object="Bangkok")]

    # Attempt 1: says Chiang Mai (wrong) → UNSAT
    # Attempt 2: says Bangkok (correct) → SAT
    llm = make_sequence_llm([
        "The company is in Chiang Mai",
        "The company is in Bangkok",
    ])

    result = generate_with_guard(
        prompt="Where is the company?",
        kb=kb,
        llm_generate=llm,
        axiom_claims=axioms,
    )

    _check("status = corrected", result.status == "corrected")
    _check("attempts = 2", result.attempts == 2)
    _check("response contains Bangkok", "Bangkok" in result.response)
    _check("history has 2 entries", len(result.history) == 2)
    _check("history[0] was hallucinating",
         result.history[0].verification.is_hallucinating)
    _check("history[1] was NOT hallucinating",
         not result.history[1].verification.is_hallucinating)
    _check("history[1].correction_prompt is not None",
         result.history[1].correction_prompt is not None)


# =====================================================================
# 3. FAILED — All attempts fail
# =====================================================================

def test_failed_all_attempts():
    print()
    print("-" * 64)
    print("  3. FAILED — All Attempts Exhausted")
    print("-" * 64)

    kb = make_location_kb()
    axioms = [Claim(subject="company", relation="location", object="Bangkok")]

    # Every attempt says Chiang Mai (always wrong)
    llm = make_fixed_llm("The company is in Chiang Mai")

    result = generate_with_guard(
        prompt="Where is the company?",
        kb=kb,
        llm_generate=llm,
        axiom_claims=axioms,
        max_retries=2,
    )

    _check("status = failed or constraint_conflict",
         result.status in ("failed", "constraint_conflict"))
    _check("attempts = 3 (1 + 2 retries)", result.attempts == 3)
    _check("max_attempts = 3", result.max_attempts == 3)
    _check("history has 3 entries", len(result.history) == 3)
    _check("all attempts hallucinating",
         all(h.verification.is_hallucinating for h in result.history))
    _check("final_verification.is_hallucinating = True",
         result.final_verification is not None and result.final_verification.is_hallucinating)


# =====================================================================
# 4. CONSTRAINT CONFLICT — Same violation every time
# =====================================================================

def test_constraint_conflict():
    print()
    print("-" * 64)
    print("  4. CONSTRAINT CONFLICT — Same Violation Every Attempt")
    print("-" * 64)

    kb = make_location_kb()
    axioms = [Claim(subject="company", relation="location", object="Bangkok")]

    # Always says wrong location — same UNSAT core every time
    llm = make_fixed_llm("The company is in Phuket")

    result = generate_with_guard(
        prompt="Where is the company?",
        kb=kb,
        llm_generate=llm,
        axiom_claims=axioms,
        max_retries=2,
    )

    _check("status = constraint_conflict", result.status == "constraint_conflict",
         f"got status={result.status}")


# =====================================================================
# 5. UNVERIFIABLE — No claims extracted
# =====================================================================

def test_unverifiable():
    print()
    print("-" * 64)
    print("  5. UNVERIFIABLE — No Claims Extracted")
    print("-" * 64)

    import axiomguard.core as core

    kb = make_location_kb()

    # Temporarily set a backend that returns no claims
    old_backend = core._llm_backend
    core._llm_backend = lambda text: []

    try:
        llm = make_fixed_llm("I have no factual claims to make.")

        result = generate_with_guard(
            prompt="Where is the company?",
            kb=kb,
            llm_generate=llm,
        )

        _check("status = unverifiable", result.status == "unverifiable")
        _check("attempts = 1", result.attempts == 1)
    finally:
        core._llm_backend = old_backend


# =====================================================================
# 6. CORRECTION PROMPT — Passed to LLM on retry
# =====================================================================

def test_correction_prompt_content():
    print()
    print("-" * 64)
    print("  6. CORRECTION PROMPT — Content Verification")
    print("-" * 64)

    kb = make_location_kb()
    axioms = [Claim(subject="company", relation="location", object="Bangkok")]

    llm = make_tracking_llm([
        "The company is in Chiang Mai",  # fail
        "The company is in Bangkok",      # pass
    ])

    result = generate_with_guard(
        prompt="Where is the company?",
        kb=kb,
        llm_generate=llm,
        axiom_claims=axioms,
    )

    # The second call should receive a correction prompt
    _check("LLM called twice", len(llm.prompts) == 2)

    correction = llm.prompts[1]
    _check("Correction prompt contains 'WHAT WENT WRONG'",
         "WHAT WENT WRONG" in correction)
    _check("Correction prompt contains 'RULES THAT WERE VIOLATED'",
         "RULES THAT WERE VIOLATED" in correction)
    _check("Correction prompt contains custom message",
         "Company can only have one location" in correction)
    _check("Correction prompt contains original question",
         "Where is the company?" in correction)

    # History records the correction prompt
    _check("history[1] has correction_prompt",
         result.history[1].correction_prompt is not None)
    _check("history[1].correction_prompt matches",
         "WHAT WENT WRONG" in result.history[1].correction_prompt)


# =====================================================================
# 7. HISTORY — Full Attempt Log
# =====================================================================

def test_history_tracking():
    print()
    print("-" * 64)
    print("  7. HISTORY — Full Attempt Log")
    print("-" * 64)

    kb = make_location_kb()
    axioms = [Claim(subject="company", relation="location", object="Bangkok")]

    llm = make_sequence_llm([
        "The company is in Chiang Mai",  # fail
        "The company is in Phuket",       # fail
        "The company is in Bangkok",      # pass
    ])

    result = generate_with_guard(
        prompt="Where?",
        kb=kb,
        llm_generate=llm,
        axiom_claims=axioms,
        max_retries=2,
    )

    _check("status = corrected", result.status == "corrected")
    _check("attempts = 3", result.attempts == 3)

    # Check each attempt
    h0 = result.history[0]
    _check("Attempt 1: Chiang Mai, hallucinating",
         "Chiang Mai" in h0.response and h0.verification.is_hallucinating)
    _check("Attempt 1: no correction_prompt", h0.correction_prompt is None)
    _check("Attempt 1: claims extracted", len(h0.claims) > 0)

    h1 = result.history[1]
    _check("Attempt 2: Phuket, hallucinating",
         "Phuket" in h1.response and h1.verification.is_hallucinating)
    _check("Attempt 2: has correction_prompt", h1.correction_prompt is not None)

    h2 = result.history[2]
    _check("Attempt 3: Bangkok, NOT hallucinating",
         "Bangkok" in h2.response and not h2.verification.is_hallucinating)
    _check("Attempt 3: has FINAL ATTEMPT prompt",
         h2.correction_prompt is not None and "FINAL ATTEMPT" in h2.correction_prompt)


# =====================================================================
# 8. TIMEOUT — Respects wall-clock limit
# =====================================================================

def test_timeout():
    print()
    print("-" * 64)
    print("  8. TIMEOUT — Wall-Clock Limit")
    print("-" * 64)

    import time

    kb = make_location_kb()
    axioms = [Claim(subject="company", relation="location", object="Bangkok")]

    # Slow LLM that sleeps
    def slow_llm(prompt: str) -> str:
        time.sleep(0.3)
        return "The company is in Chiang Mai"

    result = generate_with_guard(
        prompt="Where?",
        kb=kb,
        llm_generate=slow_llm,
        axiom_claims=axioms,
        max_retries=10,          # would take 10 retries...
        timeout_seconds=0.8,     # but we only allow 0.8s
    )

    _check("Timed out before max_retries",
         result.attempts < 11,
         f"attempts={result.attempts}")
    _check("Status is failed/constraint_conflict",
         result.status in ("failed", "constraint_conflict"))


# =====================================================================
# 9. MAX_RETRIES=0 — No retries, single attempt
# =====================================================================

def test_no_retries():
    print()
    print("-" * 64)
    print("  9. MAX_RETRIES=0 — Single Attempt Only")
    print("-" * 64)

    kb = make_location_kb()
    axioms = [Claim(subject="company", relation="location", object="Bangkok")]

    # Wrong answer, no retries allowed
    llm = make_fixed_llm("The company is in Chiang Mai")

    result = generate_with_guard(
        prompt="Where?",
        kb=kb,
        llm_generate=llm,
        axiom_claims=axioms,
        max_retries=0,
    )

    _check("status = failed", result.status in ("failed", "constraint_conflict"))
    _check("attempts = 1", result.attempts == 1)
    _check("max_attempts = 1", result.max_attempts == 1)


# =====================================================================
# 10. BACKWARD COMPAT — All previous APIs still work
# =====================================================================

def test_backward_compat():
    print()
    print("-" * 64)
    print("  10. BACKWARD COMPAT")
    print("-" * 64)

    import axiomguard

    # Old verify() works
    r = axiomguard.verify("The company is in Chiang Mai", ["The company is in Bangkok"])
    _check("verify() still works", r.is_hallucinating)

    # CorrectionResult importable
    _check("CorrectionResult importable", axiomguard.CorrectionResult is not None)
    _check("generate_with_guard importable", axiomguard.generate_with_guard is not None)


# =====================================================================
# MAIN
# =====================================================================

def main():
    print("=" * 64)
    print("  AxiomGuard v0.5.0 — Self-Correction Loop Test Suite")
    print("=" * 64)

    test_verified_first_attempt()
    test_corrected_second_attempt()
    test_failed_all_attempts()
    test_constraint_conflict()
    test_unverifiable()
    test_correction_prompt_content()
    test_history_tracking()
    test_timeout()
    test_no_retries()
    test_backward_compat()

    print()
    print("=" * 64)
    print(f"  RESULTS: {_passed}/{_total} passed")
    print("=" * 64)

    if _passed == _total:
        print()
        print("  *** v0.5.0 SELF-CORRECTION LOOP: ALL SYSTEMS GO ***")
        print()
    else:
        print()
        print(f"  WARNING: {_total - _passed} test(s) failed!")
        print()
        sys.exit(1)


if __name__ == "__main__":
    main()
