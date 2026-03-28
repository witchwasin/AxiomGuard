"""
AxiomGuard — Loan Approval Demo (RuleBuilder + Self-Correction)
================================================================

Shows how to build loan approval rules programmatically using RuleBuilder,
then verify LLM responses and auto-correct hallucinations.

No API key required — uses mock backend.

Run:
    python examples/loan_approval_demo.py
"""

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from axiomguard import RuleBuilder, Claim

# =====================================================================
# Step 1: Build rules dynamically (Mode 3 — Programmatic)
# =====================================================================

print("=" * 70)
print("  AxiomGuard — Loan Approval Demo")
print("=" * 70)
print()

print("--- Step 1: Building Rules with RuleBuilder ---")
print()

kb = (
    RuleBuilder(domain="personal_loan")
    # Register entities with Thai aliases
    .entity("applicant", aliases=["ผู้กู้", "ลูกค้า", "ผู้สมัคร"])
    # Rule: salary must be >= 15,000 THB
    .range_rule(
        "min_salary",
        entity="applicant",
        relation="salary_thb",
        min=15000,
        value_type="int",
        message="ผู้กู้ต้องมีเงินเดือนตั้งแต่ 15,000 บาทขึ้นไป",
    )
    # Rule: age must be 20-60
    .range_rule(
        "age_limit",
        entity="applicant",
        relation="age",
        min=20,
        max=60,
        value_type="int",
        message="ผู้กู้ต้องมีอายุระหว่าง 20-60 ปี",
    )
    # Rule: each applicant has one approval status
    .unique(
        "one_status",
        entity="applicant",
        relation="approval_status",
        message="สถานะอนุมัติต้องมีเพียงค่าเดียว",
    )
    .to_knowledge_base()
)

print(f"  Rules loaded: {kb.rule_count}")
print(f"  Z3 constraints: {kb.constraint_count}")
print()

# =====================================================================
# Step 2: Verify claims against rules
# =====================================================================

print("--- Step 2: Verifying Claims ---")
print()

test_cases = [
    {
        "description": "Applicant with salary 20,000 THB (valid)",
        "claims": [Claim(subject="applicant", relation="salary_thb", object="20000")],
        "expected": False,
    },
    {
        "description": "Applicant with salary 8,000 THB (too low)",
        "claims": [Claim(subject="applicant", relation="salary_thb", object="8000")],
        "expected": True,
    },
    {
        "description": "Applicant age 25 (valid)",
        "claims": [Claim(subject="applicant", relation="age", object="25")],
        "expected": False,
    },
    {
        "description": "Applicant age 17 (too young)",
        "claims": [Claim(subject="applicant", relation="age", object="17")],
        "expected": True,
    },
    {
        "description": "Conflicting approval status (approved AND rejected)",
        "claims": [
            Claim(subject="applicant", relation="approval_status", object="approved"),
        ],
        "axioms": [
            Claim(subject="applicant", relation="approval_status", object="rejected"),
        ],
        "expected": True,
    },
]

passed = 0
for case in test_cases:
    axioms = case.get("axioms")
    result = kb.verify(case["claims"], axioms)
    status = "HALLUCINATION" if result.is_hallucinating else "OK"
    match = result.is_hallucinating == case["expected"]
    passed += match

    icon = "+" if match else "x"
    print(f"  [{icon}] {case['description']}")
    print(f"      Result: {status}")
    if result.is_hallucinating:
        print(f"      Reason: {result.reason}")
    print()

print(f"--- Results: {passed}/{len(test_cases)} correct ---")
print()

# =====================================================================
# Step 3: Export rules to YAML (for sharing or version control)
# =====================================================================

print("--- Step 3: Generated YAML ---")
print()

yaml_builder = (
    RuleBuilder(domain="personal_loan")
    .entity("applicant", aliases=["ผู้กู้", "ลูกค้า"])
    .range_rule("min_salary", entity="applicant", relation="salary_thb",
                min=15000, value_type="int", message="เงินเดือนขั้นต่ำ 15,000 บาท")
    .range_rule("age_limit", entity="applicant", relation="age",
                min=20, max=60, value_type="int", message="อายุ 20-60 ปี")
    .unique("one_status", entity="applicant", relation="approval_status",
            message="สถานะอนุมัติเพียงค่าเดียว")
)

print(yaml_builder.to_yaml())
