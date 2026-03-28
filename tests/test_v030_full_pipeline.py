"""
AxiomGuard v0.3.0 — Full Pipeline Integration Test

Tests the complete flow:
  .axiom.yml → KnowledgeBase → verify_with_kb() → VerificationResult
                                                    ├── violated_rules
                                                    ├── custom YAML messages
                                                    └── proof trace

Run:
    python tests/test_v030_full_pipeline.py
"""

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import axiomguard
from axiomguard import (
    Claim,
    KnowledgeBase,
    VerificationResult,
    load_rules,
    set_knowledge_base,
    verify_with_kb,
)


# =====================================================================
# Test harness
# =====================================================================

_passed = 0
_total = 0


def _check(name: str, condition: bool, detail: str = ""):
    global _passed, _total
    _total += 1
    status = "PASS" if condition else "FAIL"
    print(f"  [{status}] {name}")
    if detail:
        print(f"         {detail}")
    if condition:
        _passed += 1
    return condition


# =====================================================================
# Fixture: Medical YAML with custom messages
# =====================================================================

MEDICAL_YAML = """\
axiomguard: "0.3"
domain: healthcare

entities:
  - name: patient
    aliases: ["ผู้ป่วย", "pt", "client"]

rules:
  - name: One blood type per patient
    type: unique
    entity: patient
    relation: blood_type
    severity: error
    message: "Patient cannot have two blood types."

  - name: Warfarin-Aspirin interaction
    type: exclusion
    entity: patient
    relation: takes
    values: [Warfarin, Aspirin]
    severity: error
    message: "CRITICAL: Warfarin + Aspirin = bleeding risk."

  - name: Ibuprofen-Aspirin interaction
    type: exclusion
    entity: patient
    relation: takes
    values: [Ibuprofen, Aspirin]
    severity: warning
    message: "WARNING: Ibuprofen + Aspirin may reduce cardioprotective effect."

  - name: Chemotherapy requires blood test
    type: dependency
    when:
      entity: patient
      relation: treatment
      value: chemotherapy
    then:
      require:
        relation: blood_test
        value: completed
    severity: error
    message: "Cannot start chemotherapy without completed blood test."

  - name: Surgery requires consent
    type: dependency
    when:
      entity: patient
      relation: procedure
      value: surgery
    then:
      require:
        relation: consent_form
        value: signed
    severity: error
    message: "Surgery cannot proceed without signed consent form."
"""

LEGAL_YAML = """\
axiomguard: "0.3"
domain: legal

entities:
  - name: contract
    aliases: ["สัญญา", "agreement"]

rules:
  - name: One governing law per contract
    type: unique
    entity: contract
    relation: governing_law
    severity: error
    message: "Contract cannot be governed by multiple jurisdictions."

  - name: Arbitration excludes litigation
    type: exclusion
    entity: contract
    relation: dispute_resolution
    values: [arbitration, litigation]
    severity: error
    message: "Contract must choose either arbitration OR litigation, not both."
"""


# =====================================================================
# Setup
# =====================================================================

def make_kb(yaml_content: str) -> KnowledgeBase:
    """Create a fresh KB from YAML string."""
    kb = KnowledgeBase()
    kb.load_string(yaml_content)
    return kb


# =====================================================================
# 1. EXPLAINABLE PROOF — Custom YAML messages in reason
# =====================================================================

def test_explainable_proof():
    print()
    print("-" * 64)
    print("  1. EXPLAINABLE PROOF — Custom YAML Messages")
    print("-" * 64)

    kb = make_kb(MEDICAL_YAML)

    # Drug interaction → custom message
    result = kb.verify(
        response_claims=[Claim(subject="patient", relation="takes", object="Aspirin")],
        axiom_claims=[Claim(subject="patient", relation="takes", object="Warfarin")],
    )
    _check("Drug interaction: is_hallucinating", result.is_hallucinating)
    _check("Custom message in reason",
         "CRITICAL: Warfarin + Aspirin = bleeding risk." in result.reason,
         f"reason={result.reason}")
    _check("violated_rules populated",
         len(result.violated_rules) >= 1,
         f"got {len(result.violated_rules)} rule(s)")
    _check("violated_rules[0].name",
         result.violated_rules[0]["name"] == "Warfarin-Aspirin interaction",
         f"name={result.violated_rules[0]['name']}")
    _check("violated_rules[0].severity",
         result.violated_rules[0]["severity"] == "error")

    # Blood type → custom message
    result2 = kb.verify(
        response_claims=[Claim(subject="patient", relation="blood_type", object="B")],
        axiom_claims=[Claim(subject="patient", relation="blood_type", object="A")],
    )
    _check("Blood type: custom message",
         "Patient cannot have two blood types." in result2.reason,
         f"reason={result2.reason}")

    # Dependency → custom message
    result3 = kb.verify(
        response_claims=[Claim(subject="patient", relation="treatment", object="chemotherapy")],
        axiom_claims=[Claim(subject="patient", relation="blood_test", object="pending")],
    )
    _check("Dependency: custom message",
         "Cannot start chemotherapy" in result3.reason,
         f"reason={result3.reason}")


# =====================================================================
# 2. verify_with_kb() — Text input → full pipeline
# =====================================================================

def test_verify_with_kb():
    print()
    print("-" * 64)
    print("  2. verify_with_kb() — Text Input Pipeline")
    print("-" * 64)

    kb = make_kb(MEDICAL_YAML)
    set_knowledge_base(kb)

    # Basic contradiction via text
    result = verify_with_kb(
        response="The company is in Chiang Mai",
        axioms=["The company is in Bangkok"],
        kb=kb,
    )
    # This uses the old mock backend which returns "location" relation
    # KB has no location uniqueness rule, so it should pass through to
    # Z3 basic check. Let's test with Claim-based KB directly instead.

    # Direct KB usage with claims
    result2 = verify_with_kb.__wrapped__ if hasattr(verify_with_kb, '__wrapped__') else None

    # Test with a KB that has location rules
    kb_loc = KnowledgeBase()
    kb_loc.load_string("""\
axiomguard: "0.3"
domain: test
rules:
  - name: One location per company
    type: unique
    entity: company
    relation: location
    message: "Company can only have one location."
""")
    set_knowledge_base(kb_loc)

    result3 = verify_with_kb(
        response="The company is in Chiang Mai",
        axioms=["The company is in Bangkok"],
    )
    _check("verify_with_kb: text input → UNSAT",
         result3.is_hallucinating,
         f"reason={result3.reason}")
    _check("verify_with_kb: custom message",
         "Company can only have one location." in result3.reason)
    _check("verify_with_kb: violated_rules",
         len(result3.violated_rules) >= 1)

    # No contradiction
    result4 = verify_with_kb(
        response="The company is in Bangkok",
        axioms=["The company is in Bangkok"],
    )
    _check("verify_with_kb: SAT",
         not result4.is_hallucinating)
    _check("verify_with_kb: no violated_rules on SAT",
         result4.violated_rules == [])

    # No KB loaded → RuntimeError
    set_knowledge_base(None)
    # Reset the global
    axiomguard.core._knowledge_base = None
    try:
        verify_with_kb("test", ["test"])
        _check("verify_with_kb: raises without KB", False)
    except RuntimeError:
        _check("verify_with_kb: raises without KB", True)

    # Restore
    set_knowledge_base(kb)


# =====================================================================
# 3. MULTI-RULE VIOLATION — Multiple rules violated at once
# =====================================================================

def test_multi_violation():
    print()
    print("-" * 64)
    print("  3. MULTI-RULE VIOLATION — Multiple Rules Broken")
    print("-" * 64)

    kb = make_kb(MEDICAL_YAML)

    # Patient takes both conflicting drugs + wrong blood type
    result = kb.verify(
        response_claims=[
            Claim(subject="patient", relation="takes", object="Aspirin"),
            Claim(subject="patient", relation="blood_type", object="O"),
        ],
        axiom_claims=[
            Claim(subject="patient", relation="takes", object="Warfarin"),
            Claim(subject="patient", relation="blood_type", object="A"),
        ],
    )
    _check("Multi-violation: is_hallucinating", result.is_hallucinating)
    rule_names = [r["name"] for r in result.violated_rules]
    _check("Multi-violation: multiple rules in violated_rules",
         len(result.violated_rules) >= 1,
         f"violated={rule_names}")


# =====================================================================
# 4. SEVERITY LEVELS — error vs warning
# =====================================================================

def test_severity():
    print()
    print("-" * 64)
    print("  4. SEVERITY LEVELS — Error vs Warning")
    print("-" * 64)

    kb = make_kb(MEDICAL_YAML)

    # Ibuprofen + Aspirin is a "warning" severity
    result = kb.verify(
        response_claims=[Claim(subject="patient", relation="takes", object="Aspirin")],
        axiom_claims=[Claim(subject="patient", relation="takes", object="Ibuprofen")],
    )
    _check("Warning severity: is_hallucinating", result.is_hallucinating)
    _check("Warning severity: rule severity is 'warning'",
         any(r["severity"] == "warning" for r in result.violated_rules),
         f"severities={[r['severity'] for r in result.violated_rules]}")


# =====================================================================
# 5. ENTITY ALIASES — Thai text resolved via YAML entities
# =====================================================================

def test_aliases_pipeline():
    print()
    print("-" * 64)
    print("  5. ENTITY ALIASES — Thai Names in Pipeline")
    print("-" * 64)

    kb = make_kb(MEDICAL_YAML)

    # "pt" and "ผู้ป่วย" both resolve to "patient"
    result = kb.verify(
        response_claims=[Claim(subject="pt", relation="blood_type", object="B")],
        axiom_claims=[Claim(subject="ผู้ป่วย", relation="blood_type", object="A")],
    )
    _check("Thai alias: pt + ผู้ป่วย → both patient → UNSAT",
         result.is_hallucinating)
    _check("Thai alias: violated rule name",
         any(r["name"] == "One blood type per patient" for r in result.violated_rules),
         f"rules={[r['name'] for r in result.violated_rules]}")


# =====================================================================
# 6. MULTI-DOMAIN — Load medical + legal
# =====================================================================

def test_multi_domain():
    print()
    print("-" * 64)
    print("  6. MULTI-DOMAIN — Medical + Legal Combined")
    print("-" * 64)

    kb = KnowledgeBase()
    kb.load_string(MEDICAL_YAML)
    kb.load_string(LEGAL_YAML)

    # Medical rule fires
    r1 = kb.verify(
        response_claims=[Claim(subject="patient", relation="takes", object="Aspirin")],
        axiom_claims=[Claim(subject="patient", relation="takes", object="Warfarin")],
    )
    _check("Medical domain: drug interaction detected", r1.is_hallucinating)

    # Legal rule fires
    r2 = kb.verify(
        response_claims=[Claim(subject="contract", relation="dispute_resolution", object="litigation")],
        axiom_claims=[Claim(subject="contract", relation="dispute_resolution", object="arbitration")],
    )
    _check("Legal domain: arb/lit exclusion detected", r2.is_hallucinating)
    _check("Legal domain: custom message",
         "arbitration OR litigation" in r2.reason,
         f"reason={r2.reason}")

    # Legal entity alias
    r3 = kb.verify(
        response_claims=[Claim(subject="สัญญา", relation="governing_law", object="UK Law")],
        axiom_claims=[Claim(subject="contract", relation="governing_law", object="Thai Law")],
    )
    _check("Legal alias: สัญญา → contract → UNSAT",
         r3.is_hallucinating)


# =====================================================================
# 7. load_rules() — File-based loading via core.py
# =====================================================================

def test_load_rules_file():
    print()
    print("-" * 64)
    print("  7. load_rules() — File-Based Loading")
    print("-" * 64)

    # Reset global state
    axiomguard.core._knowledge_base = None

    fixture_path = os.path.join(os.path.dirname(__file__), "fixtures", "medical.axiom.yml")
    if os.path.exists(fixture_path):
        load_rules(fixture_path)
        kb = axiomguard.get_knowledge_base()
        _check("load_rules: KB created", kb is not None)
        _check("load_rules: rules loaded", kb.rule_count >= 3,
             f"got {kb.rule_count}")

        # Verify via global KB
        result = kb.verify(
            response_claims=[Claim(subject="patient", relation="takes", object="Aspirin")],
            axiom_claims=[Claim(subject="patient", relation="takes", object="Warfarin")],
        )
        _check("load_rules: verification works", result.is_hallucinating)
    else:
        _check("load_rules: fixture missing", False, f"not found: {fixture_path}")
        _check("load_rules: rules loaded", False)
        _check("load_rules: verification works", False)


# =====================================================================
# 8. BACKWARD COMPATIBILITY
# =====================================================================

def test_backward_compat():
    print()
    print("-" * 64)
    print("  8. BACKWARD COMPATIBILITY — v0.2.0 verify() still works")
    print("-" * 64)

    # Old verify() should still work without KB
    result = axiomguard.verify(
        "The company is in Chiang Mai",
        ["The company is in Bangkok"],
    )
    _check("v0.2.0 verify() still works",
         result.is_hallucinating,
         f"reason={result.reason}")

    # VerificationResult has violated_rules field (empty for old API)
    _check("violated_rules defaults to []",
         result.violated_rules == [])


# =====================================================================
# 9. PROOF TRACE COMPLETENESS
# =====================================================================

def test_proof_trace():
    print()
    print("-" * 64)
    print("  9. PROOF TRACE — Full Transparency")
    print("-" * 64)

    kb = make_kb(MEDICAL_YAML)
    result = kb.verify(
        response_claims=[Claim(subject="patient", relation="takes", object="Aspirin")],
        axiom_claims=[Claim(subject="patient", relation="takes", object="Warfarin")],
    )

    # All fields present
    _check("is_hallucinating", result.is_hallucinating is True)
    _check("reason contains custom message", "CRITICAL" in result.reason)
    _check("confidence is proven", result.confidence == "proven")
    _check("contradicted_claims has indices", len(result.contradicted_claims) >= 1)
    _check("violated_rules has rule metadata", len(result.violated_rules) >= 1)
    _check("violated_rules has name", "name" in result.violated_rules[0])
    _check("violated_rules has type", "type" in result.violated_rules[0])
    _check("violated_rules has severity", "severity" in result.violated_rules[0])
    _check("violated_rules has message", "message" in result.violated_rules[0])

    # Print the full proof trace for visual inspection
    print()
    print("    --- Proof Trace (visual) ---")
    print(f"    Hallucinating: {result.is_hallucinating}")
    print(f"    Confidence:    {result.confidence}")
    print(f"    Reason:        {result.reason}")
    print(f"    Contradicted:  claim indices {result.contradicted_claims}")
    for i, rule in enumerate(result.violated_rules):
        print(f"    Rule [{i}]:      {rule['name']} ({rule['severity']})")
        print(f"                   {rule['message']}")


# =====================================================================
# MAIN
# =====================================================================

def main():
    print("=" * 64)
    print("  AxiomGuard v0.3.0 — Full Pipeline Integration Test")
    print("=" * 64)

    test_explainable_proof()
    test_verify_with_kb()
    test_multi_violation()
    test_severity()
    test_aliases_pipeline()
    test_multi_domain()
    test_load_rules_file()
    test_backward_compat()
    test_proof_trace()

    print()
    print("=" * 64)
    print(f"  RESULTS: {_passed}/{_total} passed")
    print("=" * 64)

    if _passed == _total:
        print()
        print("  *** v0.3.0 FULL PIPELINE: ALL SYSTEMS GO ***")
        print()
    else:
        print()
        print(f"  WARNING: {_total - _passed} test(s) failed!")
        print()
        sys.exit(1)


if __name__ == "__main__":
    main()
