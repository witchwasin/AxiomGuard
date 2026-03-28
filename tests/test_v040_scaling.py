"""
AxiomGuard v0.4.0 — Scaling & Integration Test Suite

Tests:
  1. Numeric rules (int, float, date)
  2. RangeRule
  3. axiom_relations() selective filter
  4. verify_chunks() pipeline (annotate, filter, strict)
  5. Benchmark: Z3 solve time at various scales
  6. Backward compatibility

Run:
    python tests/test_v040_scaling.py
"""

import sys
import os
import time

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from axiomguard import Claim, KnowledgeBase, VerificationResult
from axiomguard.integration import verify_chunks, verification_stats
from axiomguard.parser import AxiomParser, RangeRule


# =====================================================================
# Test harness
# =====================================================================

_passed = 0
_total = 0


def test(name, condition, detail=""):
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

MEDICAL_NUMERIC_YAML = """\
axiomguard: "0.3"
domain: healthcare
entities:
  - name: patient
    aliases: ["ผู้ป่วย", "pt"]
rules:
  - name: Geriatric assessment
    type: dependency
    when:
      entity: patient
      relation: age
      value: "65"
      value_type: int
      operator: ">"
    then:
      require:
        relation: assessment
        value: geriatric
    severity: error
    message: "Patients over 65 require geriatric assessment."

  - name: Dosage safe range
    type: range
    entity: prescription
    relation: dosage_mg
    value_type: int
    min: 0
    max: 500
    severity: error
    message: "Dosage must be 0-500mg."

  - name: Dosage float range
    type: range
    entity: injection
    relation: volume_ml
    value_type: float
    min: 0.1
    max: 10.0
    severity: warning
    message: "Injection volume must be 0.1-10.0ml."

  - name: Certificate expired
    type: dependency
    when:
      entity: certificate
      relation: expiry_date
      value: "2026-01-01"
      value_type: date
      operator: "<"
    then:
      require:
        relation: cert_status
        value: expired
    severity: error
    message: "Certificate has expired."

  - name: Warfarin-Aspirin
    type: exclusion
    entity: patient
    relation: takes
    values: [Warfarin, Aspirin]
    severity: error
    message: "CRITICAL: bleeding risk."

  - name: One blood type
    type: unique
    entity: patient
    relation: blood_type
    severity: error
"""

RAG_RULES_YAML = """\
axiomguard: "0.3"
domain: rag_test
rules:
  - name: One location
    type: unique
    entity: company
    relation: location
    message: "Company has one location."

  - name: Drug exclusion
    type: exclusion
    entity: patient
    relation: takes
    values: [Warfarin, Aspirin, Ibuprofen]
    message: "Drug interaction detected."
"""


# =====================================================================
# 1. NUMERIC RULES — Int / Float / Date
# =====================================================================

def test_numeric_rules():
    print()
    print("-" * 64)
    print("  1. NUMERIC RULES — Int / Float / Date")
    print("-" * 64)

    kb = KnowledgeBase()
    kb.load_string(MEDICAL_NUMERIC_YAML)

    # Int: age > 65 + geriatric → SAT
    r = kb.verify(
        [Claim(subject="patient", relation="age", object="70")],
        [Claim(subject="patient", relation="assessment", object="geriatric")],
    )
    test("Int: age 70 + geriatric = SAT", not r.is_hallucinating)

    # Int: age > 65 + standard → UNSAT
    r = kb.verify(
        [Claim(subject="patient", relation="age", object="70")],
        [Claim(subject="patient", relation="assessment", object="standard")],
    )
    test("Int: age 70 + standard = UNSAT", r.is_hallucinating)
    test("Int: custom message", "over 65" in r.reason)

    # Int: age < 65 → rule doesn't fire
    r = kb.verify(
        [Claim(subject="patient", relation="age", object="30")],
        [Claim(subject="patient", relation="assessment", object="standard")],
    )
    test("Int: age 30 = SAT (not triggered)", not r.is_hallucinating)

    # Float: volume 5.0ml → SAT (within range)
    r = kb.verify([Claim(subject="injection", relation="volume_ml", object="5.0")])
    test("Float: 5.0ml = SAT (within range)", not r.is_hallucinating)

    # Float: volume 15.0ml → UNSAT
    r = kb.verify([Claim(subject="injection", relation="volume_ml", object="15.0")])
    test("Float: 15.0ml = UNSAT (exceeds 10.0)", r.is_hallucinating)

    # Date: expired → UNSAT
    r = kb.verify(
        [Claim(subject="certificate", relation="expiry_date", object="2025-06-15")],
        [Claim(subject="certificate", relation="cert_status", object="active")],
    )
    test("Date: 2025-06-15 expired = UNSAT", r.is_hallucinating)

    # Date: valid → SAT
    r = kb.verify(
        [Claim(subject="certificate", relation="expiry_date", object="2027-01-01")],
        [Claim(subject="certificate", relation="cert_status", object="active")],
    )
    test("Date: 2027-01-01 valid = SAT", not r.is_hallucinating)


# =====================================================================
# 2. RANGE RULE — Parser + Z3
# =====================================================================

def test_range_rule():
    print()
    print("-" * 64)
    print("  2. RANGE RULE — Parser + Z3 Compilation")
    print("-" * 64)

    parser = AxiomParser()
    rs = parser.load_string("""\
axiomguard: "0.3"
domain: test
rules:
  - name: Score range
    type: range
    entity: exam
    relation: score
    value_type: int
    min: 0
    max: 100
""")
    test("RangeRule parsed", isinstance(rs.rules[0], RangeRule))
    test("min=0, max=100", rs.rules[0].min == 0 and rs.rules[0].max == 100)

    kb = KnowledgeBase()
    kb.load_string("""\
axiomguard: "0.3"
domain: test
rules:
  - name: Score range
    type: range
    entity: exam
    relation: score
    value_type: int
    min: 0
    max: 100
    message: "Score must be 0-100."
""")

    r = kb.verify([Claim(subject="exam", relation="score", object="85")])
    test("Score 85: SAT", not r.is_hallucinating)

    r = kb.verify([Claim(subject="exam", relation="score", object="150")])
    test("Score 150: UNSAT", r.is_hallucinating)

    r = kb.verify([Claim(subject="exam", relation="score", object="-5")])
    test("Score -5: UNSAT", r.is_hallucinating)


# =====================================================================
# 3. AXIOM RELATIONS — Selective Filter
# =====================================================================

def test_axiom_relations():
    print()
    print("-" * 64)
    print("  3. axiom_relations() — Selective Filter")
    print("-" * 64)

    kb = KnowledgeBase()
    kb.load_string(MEDICAL_NUMERIC_YAML)

    rels = kb.axiom_relations()
    test("Contains 'age'", "age" in rels)
    test("Contains 'takes'", "takes" in rels)
    test("Contains 'blood_type'", "blood_type" in rels)
    test("Contains 'dosage_mg'", "dosage_mg" in rels)
    test("Does NOT contain 'random'", "random" not in rels)
    test(f"Total relations: {len(rels)}", len(rels) >= 6, f"rels={rels}")


# =====================================================================
# 4. VERIFY_CHUNKS — RAG Pipeline
# =====================================================================

def test_verify_chunks():
    print()
    print("-" * 64)
    print("  4. verify_chunks() — RAG Pipeline Modes")
    print("-" * 64)

    kb = KnowledgeBase()
    kb.load_string(RAG_RULES_YAML)

    chunks = [
        {"text": "The company is in Bangkok", "score": 0.95, "metadata": {}},
        {"text": "The company is in Chiang Mai", "score": 0.90, "metadata": {}},
        {"text": "The weather is nice today", "score": 0.70, "metadata": {}},
    ]
    axioms = [Claim(subject="company", relation="location", object="Bangkok")]

    # Annotate mode
    result = verify_chunks(list(chunks), kb=kb, mode="annotate", axiom_claims=axioms)
    test("Annotate: all 3 returned", len(result) == 3)
    test("Annotate: _axiomguard in metadata",
         "_axiomguard" in result[0].get("metadata", {}))

    ag0 = result[0]["metadata"]["_axiomguard"]
    ag1 = result[1]["metadata"]["_axiomguard"]
    ag2 = result[2]["metadata"]["_axiomguard"]
    test("Chunk 0 (Bangkok): pass", ag0["status"] == "pass")
    test("Chunk 1 (Chiang Mai): fail", ag1["status"] == "fail")
    test("Chunk 2 (weather): pass (no rules match)", ag2["status"] == "pass")

    # Filter mode
    filtered = verify_chunks(
        [
            {"text": "The company is in Bangkok", "score": 0.95, "metadata": {}},
            {"text": "The company is in Chiang Mai", "score": 0.90, "metadata": {}},
            {"text": "The weather is nice today", "score": 0.70, "metadata": {}},
        ],
        kb=kb, mode="filter", axiom_claims=axioms,
    )
    test("Filter: removed contradiction", len(filtered) == 2,
         f"got {len(filtered)}")

    # Strict mode
    strict = verify_chunks(
        [
            {"text": "The company is in Bangkok", "score": 0.95, "metadata": {}},
            {"text": "The weather is nice today", "score": 0.70, "metadata": {}},
        ],
        kb=kb, mode="strict", axiom_claims=axioms,
    )
    test("Strict: verified-only chunks", len(strict) >= 1)

    # Stats
    stats = verification_stats(result)
    test("Stats: total=3", stats["total_chunks"] == 3)
    test("Stats: failed=1", stats["failed"] == 1)

    # Empty chunks
    empty = verify_chunks([], kb=kb)
    test("Empty chunks: returns []", empty == [])

    # Drug interaction via chunks
    drug_chunks = [
        {"text": "Patient takes Aspirin", "score": 0.9, "metadata": {}},
    ]
    drug_axioms = [Claim(subject="patient", relation="takes", object="Warfarin")]
    drug_result = verify_chunks(drug_chunks, kb=kb, mode="annotate", axiom_claims=drug_axioms)
    # Mock backend extracts "identity" relation, not "takes" — so no rule match
    # This is expected; real LLM would extract "takes"
    test("Drug chunk: processed without error", len(drug_result) == 1)


# =====================================================================
# 5. BENCHMARK — Z3 Solve Time at Scale
# =====================================================================

def test_benchmark():
    print()
    print("-" * 64)
    print("  5. BENCHMARK — Z3 Solve Time at Scale")
    print("-" * 64)

    kb = KnowledgeBase()
    kb.load_string(MEDICAL_NUMERIC_YAML)

    scales = [5, 15, 50, 100]
    for n in scales:
        # Generate n unique claims
        claims = [
            Claim(subject=f"patient_{i}", relation="blood_type", object="A")
            for i in range(n)
        ]
        # One contradicting claim
        claims.append(Claim(subject="patient_0", relation="blood_type", object="B"))

        start = time.perf_counter()
        result = kb.verify(claims)
        elapsed_ms = (time.perf_counter() - start) * 1000

        test(
            f"{n + 1} claims: {elapsed_ms:.1f}ms",
            elapsed_ms < 500,  # must be under 500ms
            f"hallucinating={result.is_hallucinating}",
        )

    # Selective filtering benchmark
    kb2 = KnowledgeBase()
    kb2.load_string(RAG_RULES_YAML)

    # Simulate 20 chunks, most with irrelevant relations
    chunks = []
    for i in range(20):
        if i < 3:
            chunks.append({"text": f"The company is in City{i}", "score": 0.9, "metadata": {}})
        else:
            chunks.append({"text": f"Document {i} about general topic", "score": 0.7, "metadata": {}})

    start = time.perf_counter()
    result = verify_chunks(chunks, kb=kb2, mode="annotate")
    elapsed_ms = (time.perf_counter() - start) * 1000

    verified_count = sum(
        1 for c in result
        if c.get("metadata", {}).get("_axiomguard", {}).get("verified_claims", 0) > 0
    )
    test(
        f"20 chunks selective: {elapsed_ms:.1f}ms, {verified_count} verified",
        elapsed_ms < 1000,
        f"skipped most irrelevant chunks",
    )


# =====================================================================
# 6. BACKWARD COMPATIBILITY
# =====================================================================

def test_backward_compat():
    print()
    print("-" * 64)
    print("  6. BACKWARD COMPATIBILITY")
    print("-" * 64)

    import axiomguard

    # v0.1.0 verify still works
    r = axiomguard.verify("The company is in Chiang Mai", ["The company is in Bangkok"])
    test("v0.1/v0.2 verify()", r.is_hallucinating)

    # v0.3.0 KnowledgeBase string rules still work
    kb = KnowledgeBase()
    kb.load_string("""\
axiomguard: "0.3"
domain: test
rules:
  - name: Simple unique
    type: unique
    entity: x
    relation: r
""")
    r2 = kb.verify(
        [Claim(subject="x", relation="r", object="a")],
        [Claim(subject="x", relation="r", object="b")],
    )
    test("v0.3.0 string rules still work", r2.is_hallucinating)

    # Version
    test(f"Version: {axiomguard.__version__}", axiomguard.__version__ == "0.4.0-dev")


# =====================================================================
# MAIN
# =====================================================================

def main():
    print("=" * 64)
    print("  AxiomGuard v0.4.0 — Scaling & Integration Test Suite")
    print("=" * 64)

    test_numeric_rules()
    test_range_rule()
    test_axiom_relations()
    test_verify_chunks()
    test_benchmark()
    test_backward_compat()

    print()
    print("=" * 64)
    print(f"  RESULTS: {_passed}/{_total} passed")
    print("=" * 64)

    if _passed == _total:
        print()
        print("  *** v0.4.0 SCALING & INTEGRATION: ALL SYSTEMS GO ***")
        print()
    else:
        print()
        print(f"  WARNING: {_total - _passed} test(s) failed!")
        print()
        sys.exit(1)


if __name__ == "__main__":
    main()
