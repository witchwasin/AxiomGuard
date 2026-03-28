"""
Tests for the Z3 formal contradiction engine.

Run:
    python tests/test_z3_engine.py
"""

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from axiomguard.z3_engine import check_contradiction_z3


def test(name: str, is_hallucinating: bool, reason: str, expected: bool):
    status = "PASS" if is_hallucinating == expected else "FAIL"
    print(f"  [{status}] {name}")
    if is_hallucinating != expected:
        print(f"         Expected hallucinating={expected}, got {is_hallucinating}")
        print(f"         Reason: {reason}")
    return is_hallucinating == expected


def main():
    print("=" * 64)
    print("  Z3 Engine — Formal Contradiction Tests")
    print("=" * 64)
    print()

    passed = 0
    total = 0

    # ----- Test 1: Direct contradiction (location) -----
    total += 1
    h, r = check_contradiction_z3(
        axioms_sro=[{"subject": "company", "relation": "location", "object": "Bangkok"}],
        response_sro={"subject": "company", "relation": "location", "object": "Chiang Mai"},
    )
    if test("Location contradiction: Bangkok vs Chiang Mai", h, r, expected=True):
        passed += 1

    # ----- Test 2: No contradiction (same value) -----
    total += 1
    h, r = check_contradiction_z3(
        axioms_sro=[{"subject": "company", "relation": "location", "object": "Bangkok"}],
        response_sro={"subject": "company", "relation": "location", "object": "Bangkok"},
    )
    if test("Same location: Bangkok == Bangkok", h, r, expected=False):
        passed += 1

    # ----- Test 3: Different subjects — no contradiction -----
    total += 1
    h, r = check_contradiction_z3(
        axioms_sro=[{"subject": "company", "relation": "location", "object": "Bangkok"}],
        response_sro={"subject": "branch", "relation": "location", "object": "Chiang Mai"},
    )
    if test("Different subjects: company vs branch (no contradiction)", h, r, expected=False):
        passed += 1

    # ----- Test 4: Identity contradiction (CEO) -----
    total += 1
    h, r = check_contradiction_z3(
        axioms_sro=[{"subject": "ceo", "relation": "identity", "object": "Somchai"}],
        response_sro={"subject": "ceo", "relation": "identity", "object": "John"},
    )
    if test("Identity contradiction: CEO Somchai vs John", h, r, expected=True):
        passed += 1

    # ----- Test 5: Multiple axioms, one contradiction -----
    total += 1
    h, r = check_contradiction_z3(
        axioms_sro=[
            {"subject": "company", "relation": "location", "object": "Bangkok"},
            {"subject": "ceo", "relation": "identity", "object": "Somchai"},
            {"subject": "product", "relation": "identity", "object": "AxiomGuard"},
        ],
        response_sro={"subject": "company", "relation": "location", "object": "Phuket"},
    )
    if test("Multiple axioms, location contradiction: Bangkok vs Phuket", h, r, expected=True):
        passed += 1

    # ----- Test 6: Multiple axioms, no contradiction -----
    total += 1
    h, r = check_contradiction_z3(
        axioms_sro=[
            {"subject": "company", "relation": "location", "object": "Bangkok"},
            {"subject": "ceo", "relation": "identity", "object": "Somchai"},
        ],
        response_sro={"subject": "product", "relation": "identity", "object": "AxiomGuard"},
    )
    if test("Multiple axioms, unrelated response (no contradiction)", h, r, expected=False):
        passed += 1

    # ----- Test 7: Non-exclusive relation — no contradiction -----
    total += 1
    h, r = check_contradiction_z3(
        axioms_sro=[{"subject": "company", "relation": "attribute", "object": "innovative"}],
        response_sro={"subject": "company", "relation": "attribute", "object": "profitable"},
    )
    if test("Non-exclusive relation 'attribute': innovative + profitable (no contradiction)", h, r, expected=False):
        passed += 1

    print()
    print(f"  Results: {passed}/{total} passed")

    if passed < total:
        sys.exit(1)


if __name__ == "__main__":
    main()
