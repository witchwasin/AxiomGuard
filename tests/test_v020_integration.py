"""
AxiomGuard v0.2.0 — Integration Test Suite

Tests the complete 5-stage pipeline:
  LLM Extract → Parse → Schema → Semantic → Entity Resolve → Z3 Prove

All tests use the Mock backend (no API calls, runs fast).

Run:
    python tests/test_v020_integration.py
"""

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from axiomguard import (
    Claim,
    EntityResolver,
    ExtractionResult,
    VerificationResult,
    extract_claims,
    set_entity_resolver,
    set_llm_backend,
    verify,
)
from axiomguard.backends import (
    check_semantics,
    parse_raw_json,
    validate_and_extract,
    validate_schema,
)
from axiomguard.resolver import EntityResolver as _ER
from axiomguard.z3_engine import check_claims


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
    if not condition and detail:
        pass  # detail already printed
    if condition:
        _passed += 1
    return condition


# =====================================================================
# Setup
# =====================================================================

def setup():
    """Reset to default mock backend + resolver with Thai aliases."""
    from axiomguard.core import _mock_llm_extract
    set_llm_backend(_mock_llm_extract)
    set_entity_resolver(EntityResolver(aliases={
        "กทม": "Bangkok",
        "tn": "Thana City",
    }))


# =====================================================================
# 1. MODELS — Pydantic validation
# =====================================================================

def test_models():
    print()
    print("-" * 64)
    print("  1. MODELS — Pydantic Schema Validation")
    print("-" * 64)

    # Valid claim
    c = Claim(subject="company", relation="location", object="Bangkok")
    _check("Create valid Claim", c.subject == "company")

    # Negated claim
    cn = Claim(subject="Paris", relation="capital", object="Germany", negated=True)
    _check("Create negated Claim", cn.negated is True)

    # Dedup key
    c1 = Claim(subject="A", relation="r", object="B")
    c2 = Claim(subject="B", relation="r", object="A")
    _check("as_key() is order-independent", c1.as_key() == c2.as_key(),
         f"{c1.as_key()} == {c2.as_key()}")

    # Schema rejects empty subject
    try:
        Claim(subject="", relation="r", object="o")
        _check("Reject empty subject", False)
    except Exception:
        _check("Reject empty subject", True)

    # ExtractionResult rejects empty claims list
    try:
        ExtractionResult(claims=[])
        _check("Reject empty claims list", False)
    except Exception:
        _check("Reject empty claims list", True)

    # VerificationResult backward compat
    vr = VerificationResult(is_hallucinating=True, reason="test")
    _check("VerificationResult backward compat",
         vr.confidence == "proven" and vr.extraction_warnings == [])


# =====================================================================
# 2. ENTITY RESOLVER — Canonicalization Pipeline
# =====================================================================

def test_resolver():
    print()
    print("-" * 64)
    print("  2. ENTITY RESOLVER — Canonicalization Pipeline")
    print("-" * 64)

    r = _ER(aliases={"กทม": "Bangkok", "cnx": "Chiang Mai"})

    # Known aliases
    canon, hit = r.resolve("BKK")
    _check("BKK → Bangkok", canon == "Bangkok" and hit)

    canon, hit = r.resolve("กทม")
    _check("กทม → Bangkok", canon == "Bangkok" and hit)

    canon, hit = r.resolve("headquarters")
    _check("headquarters → company", canon == "company" and hit)

    # Unknown entity stays distinct (conservative)
    canon, hit = r.resolve("Timbuktu")
    _check("Unknown stays distinct", canon == "Timbuktu" and not hit)

    # add_aliases at runtime
    r.add_aliases({"สวนหลวง": "Suanluang Rama IX"})
    canon, hit = r.resolve("สวนหลวง")
    _check("add_aliases works", canon == "Suanluang Rama IX" and hit)

    # resolve_claim transforms subject + object
    c = Claim(subject="HQ", relation="location", object="BKK")
    resolved, warnings = r.resolve_claim(c)
    _check("resolve_claim: HQ→company, BKK→Bangkok",
         resolved.subject == "company" and resolved.object == "Bangkok",
         f"subject={resolved.subject}, object={resolved.object}")


# =====================================================================
# 3. VALIDATION PIPELINE — Stages 1-3
# =====================================================================

def test_validation_pipeline():
    print()
    print("-" * 64)
    print("  3. VALIDATION PIPELINE — Parse → Schema → Semantic")
    print("-" * 64)

    # Stage 1: Parse — markdown fences
    raw_md = '```json\n{"claims": [{"subject": "X", "relation": "r", "object": "Y", "negated": false}]}\n```'
    data = parse_raw_json(raw_md)
    _check("Parse: strip markdown fences", "claims" in data)

    # Stage 1: Parse — trailing commas
    raw_comma = '{"claims": [{"subject": "X", "relation": "r", "object": "Y", "negated": false,},]}'
    data2 = parse_raw_json(raw_comma)
    _check("Parse: fix trailing commas", len(data2["claims"]) == 1)

    # Stage 2: Schema validation
    extraction = validate_schema(data)
    _check("Schema: valid ExtractionResult", len(extraction.claims) == 1)

    # Stage 3: Semantic — negation warning
    claims_no_neg = [Claim(subject="Paris", relation="capital", object="Germany")]
    filtered, warnings = check_semantics(claims_no_neg, "Paris is NOT the capital of Germany")
    _check("Semantic: negation warning fires",
         any("negation" in w.lower() for w in warnings),
         f"warnings={warnings[0][:60]}..." if warnings else "NO WARNING")

    # Stage 3: Semantic — dedup
    dupes = [
        Claim(subject="A", relation="r", object="B"),
        Claim(subject="A", relation="r", object="B"),
    ]
    filtered, warnings = check_semantics(dupes, "")
    _check("Semantic: dedup removes duplicates",
         len(filtered) == 1 and any("duplicate" in w.lower() for w in warnings))

    # Stage 3: Semantic — non-grounded filtered
    verbose = [Claim(
        subject="X", relation="location",
        object="a very large metropolitan city located somewhere in the remote northern mountainous region of Southeast Asia"
    )]
    filtered, warnings = check_semantics(verbose, "")
    _check("Semantic: non-grounded object filtered",
         len(filtered) == 0 and any("non-grounded" in w.lower() for w in warnings))

    # Stage 3: Semantic — compound relation filtered
    compound = [Claim(subject="X", relation="location and founder", object="Y")]
    filtered, warnings = check_semantics(compound, "")
    _check("Semantic: compound relation filtered",
         len(filtered) == 0 and any("non-atomic" in w.lower() for w in warnings))

    # Combined pipeline
    raw_full = '{"claims": [{"subject": "company", "relation": "location", "object": "Bangkok", "negated": false}]}'
    claims, warnings = validate_and_extract(raw_full, "The company is in Bangkok")
    _check("Full pipeline: parse → schema → semantic",
         len(claims) == 1 and claims[0].subject == "company")


# =====================================================================
# 4. Z3 ENGINE — Assumptions API + unsat_core
# =====================================================================

def test_z3_engine():
    print()
    print("-" * 64)
    print("  4. Z3 ENGINE — Assumptions API + unsat_core")
    print("-" * 64)

    # Single contradiction
    axioms = [Claim(subject="company", relation="location", object="Bangkok")]
    response = [Claim(subject="company", relation="location", object="Chiang Mai")]
    h, reason, indices = check_claims(axioms, response)
    _check("Single contradiction detected", h and 0 in indices,
         f"indices={indices}")

    # No contradiction
    response_ok = [Claim(subject="company", relation="location", object="Bangkok")]
    h2, _, indices2 = check_claims(axioms, response_ok)
    _check("No contradiction: SAT", not h2 and indices2 == [])

    # Multi-claim: pinpoint the bad one
    response_multi = [
        Claim(subject="company", relation="identity", object="TechCorp"),
        Claim(subject="company", relation="location", object="Phuket"),
    ]
    h3, reason3, indices3 = check_claims(axioms, response_multi)
    _check("Multi-claim: pinpoints claim[1]", h3 and 1 in indices3,
         f"indices={indices3}, reason={reason3}")

    # Negated claim: "NOT capital of Germany" doesn't contradict "capital of France"
    ax_cap = [Claim(subject="Paris", relation="capital", object="France")]
    resp_neg = [Claim(subject="Paris", relation="capital", object="Germany", negated=True)]
    h4, _, _ = check_claims(ax_cap, resp_neg)
    _check("Negated claim: no false contradiction", not h4)

    # Multiple axioms + multiple contradictions
    axioms_big = [
        Claim(subject="company", relation="location", object="Bangkok"),
        Claim(subject="CEO", relation="identity", object="Somchai"),
        Claim(subject="product", relation="identity", object="AxiomGuard"),
    ]
    response_big = [
        Claim(subject="company", relation="location", object="Phuket"),
        Claim(subject="CEO", relation="identity", object="John"),
        Claim(subject="product", relation="identity", object="AxiomGuard"),
    ]
    h5, reason5, indices5 = check_claims(axioms_big, response_big)
    _check("Multi-axiom: detects contradiction(s)", h5 and len(indices5) >= 1,
         f"indices={indices5}")

    # Non-exclusive relation: no contradiction
    ax_attr = [Claim(subject="company", relation="attribute", object="innovative")]
    resp_attr = [Claim(subject="company", relation="attribute", object="profitable")]
    h6, _, _ = check_claims(ax_attr, resp_attr)
    _check("Non-exclusive relation: both attributes coexist", not h6)

    # Timeout: 50 axioms still completes
    ax_many = [Claim(subject=f"s{i}", relation="location", object=f"city{i}") for i in range(50)]
    resp_to = [Claim(subject="s0", relation="location", object="wrong")]
    h7, _, _ = check_claims(ax_many, resp_to, timeout_ms=2000)
    _check("50 axioms within timeout", h7)


# =====================================================================
# 5. END-TO-END — Full pipeline via verify()
# =====================================================================

def test_end_to_end():
    print()
    print("-" * 64)
    print("  5. END-TO-END — verify() full pipeline")
    print("-" * 64)

    setup()

    # Basic contradiction
    r = verify("The company is in Chiang Mai", ["The company is in Bangkok"])
    _check("E2E: contradiction detected",
         r.is_hallucinating and r.confidence == "proven",
         f"confidence={r.confidence}, contradicted={r.contradicted_claims}")

    # No contradiction
    r2 = verify("The company is in Bangkok", ["The company is in Bangkok"])
    _check("E2E: no contradiction",
         not r2.is_hallucinating and r2.confidence == "proven")

    # Entity resolution via verify: HQ→company, BKK→Bangkok
    r3 = verify("HQ is in BKK", ["The company is in Bangkok"])
    _check("E2E: entity resolution (HQ=company, BKK=Bangkok) → no contradiction",
         not r3.is_hallucinating,
         f"hallucinating={r3.is_hallucinating}")

    # Entity resolution: BKK vs Chiang Mai → contradiction
    r4 = verify("HQ is in Chiang Mai", ["The company is in Bangkok"])
    _check("E2E: entity resolution + contradiction",
         r4.is_hallucinating,
         f"reason={r4.reason}")

    # Multiple axioms, one contradiction
    r5 = verify(
        "The company is in Phuket",
        ["The company is in Bangkok", "The CEO is Somchai"],
    )
    _check("E2E: multi-axiom, pinpoints contradiction",
         r5.is_hallucinating and 0 in r5.contradicted_claims,
         f"contradicted={r5.contradicted_claims}")

    # extract_claims resolves entities
    claims = extract_claims("HQ is in BKK")
    _check("extract_claims: HQ→company, BKK→Bangkok",
         claims[0].subject == "company" and claims[0].object == "Bangkok",
         f"subject={claims[0].subject}, object={claims[0].object}")


# =====================================================================
# 6. BACKWARD COMPATIBILITY — v0.1.0 interfaces still work
# =====================================================================

def test_backward_compat():
    print()
    print("-" * 64)
    print("  6. BACKWARD COMPATIBILITY — v0.1.0 interfaces")
    print("-" * 64)

    setup()

    # translate_to_logic returns dict
    from axiomguard import translate_to_logic
    triple = translate_to_logic("The company is in Bangkok")
    _check("translate_to_logic returns dict",
         isinstance(triple, dict) and "subject" in triple and "relation" in triple)

    # check_contradiction_z3 (old signature)
    from axiomguard.z3_engine import check_contradiction_z3
    h, reason = check_contradiction_z3(
        [{"subject": "company", "relation": "location", "object": "Bangkok"}],
        {"subject": "company", "relation": "location", "object": "Chiang Mai"},
    )
    _check("check_contradiction_z3 (dict API)", h,
         f"reason={reason}")

    # parse_response (old function)
    from axiomguard.backends import parse_response
    d = parse_response('{"subject": "X", "relation": "r", "object": "Y"}')
    _check("parse_response (v0.1.0 compat)", d["subject"] == "X")

    # set_llm_backend with dict-returning function (auto-wrap)
    def old_backend(text: str) -> dict:
        return {"subject": "test", "relation": "identity", "object": "value"}

    set_llm_backend(old_backend)
    r = verify("test", ["test"])
    _check("set_llm_backend with dict-returning backend",
         isinstance(r, VerificationResult))

    # Restore mock
    setup()


# =====================================================================
# MAIN
# =====================================================================

def main():
    print("=" * 64)
    print("  AxiomGuard v0.2.0 — Integration Test Suite")
    print("=" * 64)

    test_models()
    test_resolver()
    test_validation_pipeline()
    test_z3_engine()
    test_end_to_end()
    test_backward_compat()

    print()
    print("=" * 64)
    print(f"  RESULTS: {_passed}/{_total} passed")
    print("=" * 64)

    if _passed == _total:
        print()
        print("  *** v0.2.0 INTEGRATION TEST: ALL SYSTEMS GO ***")
        print()
    else:
        print()
        print(f"  WARNING: {_total - _passed} test(s) failed!")
        print()
        sys.exit(1)


if __name__ == "__main__":
    main()
