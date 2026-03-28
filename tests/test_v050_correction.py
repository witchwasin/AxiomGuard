"""
AxiomGuard v0.5.0 — Correction Engine Test Suite

Tests:
  1. CorrectionAttempt and CorrectionResult data models
  2. build_correction_prompt() with UNSAT results
  3. Violation details — specific claim identification
  4. Rule list — YAML custom messages
  5. Verified claims — preserve section
  6. Final retry escalation prompt
  7. Edge cases

Run:
    python tests/test_v050_correction.py
"""

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from axiomguard.models import (
    Claim,
    CorrectionAttempt,
    CorrectionResult,
    VerificationResult,
)
from axiomguard.correction import (
    build_correction_prompt,
    _build_violation_details,
    _build_rule_list,
    _build_verified_claims,
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
# Fixtures
# =====================================================================

def make_drug_interaction_result():
    """Simulates: patient takes Warfarin (axiom) + Aspirin (response) → UNSAT."""
    claims = [
        Claim(subject="patient", relation="takes", object="Warfarin"),
        Claim(subject="patient", relation="takes", object="Aspirin"),
    ]
    verification = VerificationResult(
        is_hallucinating=True,
        reason="Z3 proved contradiction (UNSAT): CRITICAL: Warfarin + Aspirin = bleeding risk.",
        confidence="proven",
        contradicted_claims=[1],  # claim[1] = Aspirin
        violated_rules=[{
            "name": "Warfarin-Aspirin interaction",
            "type": "exclusion",
            "severity": "error",
            "message": "CRITICAL: Warfarin + Aspirin = bleeding risk.",
        }],
    )
    return claims, verification


def make_multi_violation_result():
    """Simulates: blood type conflict + drug interaction simultaneously."""
    claims = [
        Claim(subject="patient", relation="blood_type", object="B"),
        Claim(subject="patient", relation="takes", object="Aspirin"),
        Claim(subject="patient", relation="assessment", object="standard"),
    ]
    verification = VerificationResult(
        is_hallucinating=True,
        reason="Z3 proved contradiction (UNSAT): multiple violations",
        confidence="proven",
        contradicted_claims=[0, 1],
        violated_rules=[
            {
                "name": "One blood type per patient",
                "type": "unique",
                "severity": "error",
                "message": "Patient cannot have two blood types.",
            },
            {
                "name": "Warfarin-Aspirin interaction",
                "type": "exclusion",
                "severity": "error",
                "message": "CRITICAL: Warfarin + Aspirin = bleeding risk.",
            },
        ],
    )
    return claims, verification


def make_no_rules_result():
    """Simulates: UNSAT but no violated_rules matched (fallback path)."""
    claims = [
        Claim(subject="x", relation="r", object="a"),
    ]
    verification = VerificationResult(
        is_hallucinating=True,
        reason="Z3 proved contradiction (UNSAT): x.r cannot be both 'b' (axiom) and 'a' (response)",
        confidence="proven",
        contradicted_claims=[0],
        violated_rules=[],
    )
    return claims, verification


# =====================================================================
# 1. DATA MODELS
# =====================================================================

def test_models():
    print()
    print("-" * 64)
    print("  1. DATA MODELS — CorrectionAttempt / CorrectionResult")
    print("-" * 64)

    # CorrectionAttempt
    attempt = CorrectionAttempt(
        attempt_number=1,
        response="Patient takes Warfarin and Aspirin.",
        claims=[Claim(subject="patient", relation="takes", object="Warfarin")],
        verification=VerificationResult(is_hallucinating=True, reason="UNSAT"),
        correction_prompt=None,
    )
    _check("CorrectionAttempt creation", attempt.attempt_number == 1)
    _check("CorrectionAttempt.correction_prompt None for attempt 1",
         attempt.correction_prompt is None)

    # CorrectionResult — verified
    result = CorrectionResult(
        status="verified",
        response="Patient takes Warfarin only.",
        attempts=1,
        max_attempts=3,
        history=[attempt],
        final_verification=VerificationResult(is_hallucinating=False, reason="SAT"),
    )
    _check("CorrectionResult status='verified'", result.status == "verified")
    _check("CorrectionResult.attempts=1", result.attempts == 1)

    # CorrectionResult — corrected
    result2 = CorrectionResult(
        status="corrected",
        response="Fixed response",
        attempts=2,
        max_attempts=3,
    )
    _check("CorrectionResult status='corrected'", result2.status == "corrected")

    # CorrectionResult — failed
    result3 = CorrectionResult(
        status="failed",
        response="Last attempt",
        attempts=3,
        max_attempts=3,
    )
    _check("CorrectionResult status='failed'", result3.status == "failed")

    # CorrectionResult — constraint_conflict
    result4 = CorrectionResult(
        status="constraint_conflict",
        response="",
        attempts=3,
        max_attempts=3,
    )
    _check("CorrectionResult status='constraint_conflict'",
         result4.status == "constraint_conflict")

    # CorrectionResult — unverifiable
    result5 = CorrectionResult(
        status="unverifiable",
        response="I cannot provide that information.",
        attempts=1,
        max_attempts=3,
    )
    _check("CorrectionResult status='unverifiable'",
         result5.status == "unverifiable")


# =====================================================================
# 2. CORRECTION PROMPT — Drug Interaction
# =====================================================================

def test_drug_interaction_prompt():
    print()
    print("-" * 64)
    print("  2. CORRECTION PROMPT — Drug Interaction")
    print("-" * 64)

    claims, verification = make_drug_interaction_result()

    prompt = build_correction_prompt(
        original_prompt="What medications is Patient John taking?",
        response="Patient John takes Warfarin and Aspirin daily.",
        claims=claims,
        verification=verification,
    )

    # Contains key sections
    _check("Contains 'WHAT WENT WRONG'", "WHAT WENT WRONG" in prompt)
    _check("Contains 'RULES THAT WERE VIOLATED'", "RULES THAT WERE VIOLATED" in prompt)
    _check("Contains 'WHAT WAS CORRECT'", "WHAT WAS CORRECT" in prompt)
    _check("Contains 'YOUR TASK'", "YOUR TASK" in prompt)
    _check("Contains original prompt",
         "What medications is Patient John taking?" in prompt)

    # Violation details — specific claim
    _check("Names the wrong claim: 'takes Aspirin'",
         "takes Aspirin" in prompt,
         f"checking for 'takes Aspirin' in prompt")
    _check("Marks it as WRONG",
         "WRONG" in prompt)

    # YAML custom message
    _check("Contains custom rule message: 'bleeding risk'",
         "bleeding risk" in prompt)
    _check("Contains rule name: 'Warfarin-Aspirin interaction'",
         "Warfarin-Aspirin interaction" in prompt)
    _check("Contains severity: [ERROR]",
         "[ERROR]" in prompt)

    # Preserve section — Warfarin should be preserved
    _check("Preserve section contains Warfarin",
         "takes Warfarin" in prompt)

    # Does NOT contain apology instruction
    _check("Contains 'Do NOT apologize'",
         "Do NOT apologize" in prompt)


# =====================================================================
# 3. VIOLATION DETAILS — Specific Claim Identification
# =====================================================================

def test_violation_details():
    print()
    print("-" * 64)
    print("  3. VIOLATION DETAILS — Specific Claim Identification")
    print("-" * 64)

    # Single violation
    claims, verification = make_drug_interaction_result()
    details = _build_violation_details(claims, verification)
    _check("Single violation: mentions Aspirin",
         "Aspirin" in details)
    _check("Single violation: includes rule message",
         "bleeding risk" in details)

    # Multi violation
    claims2, verification2 = make_multi_violation_result()
    details2 = _build_violation_details(claims2, verification2)
    _check("Multi violation: mentions blood_type B",
         "blood_type" in details2 and "B" in details2)
    _check("Multi violation: mentions Aspirin",
         "Aspirin" in details2)

    # Negated claim
    neg_claims = [Claim(subject="Paris", relation="capital", object="Germany", negated=True)]
    neg_ver = VerificationResult(
        is_hallucinating=True,
        reason="contradiction",
        contradicted_claims=[0],
        violated_rules=[],
    )
    neg_details = _build_violation_details(neg_claims, neg_ver)
    _check("Negated claim: shows NOT",
         "NOT" in neg_details)


# =====================================================================
# 4. RULE LIST — YAML Custom Messages
# =====================================================================

def test_rule_list():
    print()
    print("-" * 64)
    print("  4. RULE LIST — YAML Custom Messages")
    print("-" * 64)

    _, verification = make_drug_interaction_result()
    rules = _build_rule_list(verification)
    _check("Rule list: numbered", rules.startswith("1."))
    _check("Rule list: severity tag", "[ERROR]" in rules)
    _check("Rule list: rule name", "Warfarin-Aspirin interaction" in rules)
    _check("Rule list: custom message", "bleeding risk" in rules)

    # Multi rules
    _, verification2 = make_multi_violation_result()
    rules2 = _build_rule_list(verification2)
    _check("Multi rules: has rule 1 and 2", "1." in rules2 and "2." in rules2)

    # No rules fallback
    _, no_rules_ver = make_no_rules_result()
    rules3 = _build_rule_list(no_rules_ver)
    _check("No rules: fallback to reason", "cannot be both" in rules3)


# =====================================================================
# 5. VERIFIED CLAIMS — Preserve Section
# =====================================================================

def test_verified_claims():
    print()
    print("-" * 64)
    print("  5. VERIFIED CLAIMS — Preserve Section")
    print("-" * 64)

    claims, verification = make_drug_interaction_result()
    preserved = _build_verified_claims(claims, verification)

    # claim[0] = Warfarin (not contradicted) should be preserved
    _check("Warfarin in preserve list", "Warfarin" in preserved)
    # claim[1] = Aspirin (contradicted) should NOT be in preserve list
    _check("Aspirin NOT in preserve list", "Aspirin" not in preserved)

    # Multi violation — only claim[2] preserved
    claims2, verification2 = make_multi_violation_result()
    preserved2 = _build_verified_claims(claims2, verification2)
    _check("Multi: assessment preserved", "assessment" in preserved2)
    _check("Multi: blood_type NOT preserved", "blood_type" not in preserved2)

    # All contradicted
    all_bad_ver = VerificationResult(
        is_hallucinating=True,
        reason="all wrong",
        contradicted_claims=[0],
    )
    all_bad = _build_verified_claims(
        [Claim(subject="x", relation="r", object="a")],
        all_bad_ver,
    )
    _check("All contradicted: regenerate message",
         "regenerate entirely" in all_bad.lower())


# =====================================================================
# 6. FINAL RETRY ESCALATION
# =====================================================================

def test_escalation():
    print()
    print("-" * 64)
    print("  6. FINAL RETRY — Escalation Prompt")
    print("-" * 64)

    claims, verification = make_drug_interaction_result()

    # Normal prompt (attempt 1 of 3)
    normal = build_correction_prompt(
        original_prompt="test",
        response="test",
        claims=claims,
        verification=verification,
        attempt_number=1,
        max_attempts=3,
    )
    _check("Attempt 1: uses normal template",
         "WHAT WENT WRONG" in normal and "FINAL ATTEMPT" not in normal)

    # Final attempt (attempt 2 of 3 → uses escalation)
    final = build_correction_prompt(
        original_prompt="test question",
        response="test",
        claims=claims,
        verification=verification,
        attempt_number=2,
        max_attempts=3,
    )
    _check("Final attempt: uses escalation template",
         "FINAL ATTEMPT" in final)
    _check("Final attempt: mentions previous attempts",
         "previous 2 attempts" in final)
    _check("Final attempt: contains MANDATORY CONSTRAINTS",
         "MANDATORY CONSTRAINTS" in final)
    _check("Final attempt: contains original prompt",
         "test question" in final)


# =====================================================================
# 7. EDGE CASES
# =====================================================================

def test_edge_cases():
    print()
    print("-" * 64)
    print("  7. EDGE CASES")
    print("-" * 64)

    # Empty claims list
    empty_ver = VerificationResult(
        is_hallucinating=True,
        reason="contradiction",
        contradicted_claims=[0],
        violated_rules=[],
    )
    prompt = build_correction_prompt(
        original_prompt="test",
        response="test",
        claims=[],
        verification=empty_ver,
    )
    _check("Empty claims: still generates prompt", len(prompt) > 50)

    # Contradicted index out of bounds
    oob_ver = VerificationResult(
        is_hallucinating=True,
        reason="test",
        contradicted_claims=[99],
        violated_rules=[],
    )
    prompt2 = build_correction_prompt(
        original_prompt="test",
        response="test",
        claims=[Claim(subject="x", relation="r", object="a")],
        verification=oob_ver,
    )
    _check("OOB index: handled gracefully", "index 99" in prompt2)

    # Rule with empty message
    empty_msg_ver = VerificationResult(
        is_hallucinating=True,
        reason="Z3 proved contradiction (UNSAT): x.r conflict",
        contradicted_claims=[0],
        violated_rules=[{"name": "Rule X", "type": "unique", "severity": "error", "message": ""}],
    )
    prompt3 = build_correction_prompt(
        original_prompt="test",
        response="test",
        claims=[Claim(subject="x", relation="r", object="a")],
        verification=empty_msg_ver,
    )
    _check("Empty rule message: fallback to reason", "x.r conflict" in prompt3)


# =====================================================================
# MAIN
# =====================================================================

def main():
    print("=" * 64)
    print("  AxiomGuard v0.5.0 — Correction Engine Test Suite")
    print("=" * 64)

    test_models()
    test_drug_interaction_prompt()
    test_violation_details()
    test_rule_list()
    test_verified_claims()
    test_escalation()
    test_edge_cases()

    print()
    print("=" * 64)
    print(f"  RESULTS: {_passed}/{_total} passed")
    print("=" * 64)

    if _passed == _total:
        print()
        print("  *** v0.5.0 CORRECTION ENGINE: ALL SYSTEMS GO ***")
        print()
    else:
        print()
        print(f"  WARNING: {_total - _passed} test(s) failed!")
        print()
        sys.exit(1)


if __name__ == "__main__":
    main()
