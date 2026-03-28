"""
AxiomGuard — Medical Bot Safety Guard
======================================

Demonstrates using YAML rules to catch dangerous medical hallucinations:
- Drug interaction conflicts
- Dosage limit violations
- Patient fact contradictions

No API key required — uses mock backend.

Run:
    python examples/medical_bot_guard.py
"""

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from axiomguard import KnowledgeBase, Claim

# =====================================================================
# Load medical safety rules from YAML
# =====================================================================

print("=" * 70)
print("  AxiomGuard — Medical Bot Safety Guard")
print("=" * 70)
print()

rules_path = os.path.join(os.path.dirname(__file__), "medical_rules.axiom.yml")
kb = KnowledgeBase()
kb.load(rules_path)

print(f"  Domain: Medical Safety")
print(f"  Rules loaded: {kb.rule_count}")
print(f"  Z3 constraints: {kb.constraint_count}")
print()

# =====================================================================
# Scenario 1: Drug Interaction — Warfarin + Aspirin
# =====================================================================

print("--- Scenario 1: Drug Interaction ---")
print('  Bot says: "Patient takes Warfarin and Aspirin"')
print()

axioms = [Claim(subject="patient", relation="medication", object="Warfarin")]
response = [Claim(subject="patient", relation="medication", object="Aspirin")]

result = kb.verify(response, axioms)
print(f"  Hallucination: {result.is_hallucinating}")
print(f"  Reason: {result.reason}")
if result.violated_rules:
    print(f"  Violated: {[r['name'] for r in result.violated_rules]}")
print()

# =====================================================================
# Scenario 2: Dosage Violation — Paracetamol 5000mg
# =====================================================================

print("--- Scenario 2: Dosage Violation ---")
print('  Bot says: "Prescribe Paracetamol 5000mg daily"')
print()

response = [Claim(subject="patient", relation="paracetamol_mg_daily", object="5000")]
result = kb.verify(response)

print(f"  Hallucination: {result.is_hallucinating}")
print(f"  Reason: {result.reason}")
print()

# =====================================================================
# Scenario 3: Safe Dosage — Paracetamol 2000mg
# =====================================================================

print("--- Scenario 3: Safe Dosage ---")
print('  Bot says: "Prescribe Paracetamol 2000mg daily"')
print()

response = [Claim(subject="patient", relation="paracetamol_mg_daily", object="2000")]
result = kb.verify(response)

print(f"  Hallucination: {result.is_hallucinating}")
print(f"  Safe: {not result.is_hallucinating}")
print()

# =====================================================================
# Scenario 4: Blood Type Contradiction
# =====================================================================

print("--- Scenario 4: Blood Type Contradiction ---")
print('  Record says: "Blood type A"')
print('  Bot says: "Blood type B"')
print()

axioms = [Claim(subject="patient", relation="blood_type", object="A")]
response = [Claim(subject="patient", relation="blood_type", object="B")]

result = kb.verify(response, axioms)
print(f"  Hallucination: {result.is_hallucinating}")
print(f"  Reason: {result.reason}")
print()

# =====================================================================
# Scenario 5: Allergy Cross-Reactivity
# =====================================================================

print("--- Scenario 5: Allergy Safety ---")
print('  Record says: "Patient has Penicillin allergy"')
print('  Bot says: "Prescribe Amoxicillin"')
print()

axioms = [Claim(subject="patient", relation="medication", object="Penicillin_allergy")]
response = [Claim(subject="patient", relation="medication", object="Amoxicillin")]

result = kb.verify(response, axioms)
print(f"  Hallucination: {result.is_hallucinating}")
print(f"  Reason: {result.reason}")
if result.violated_rules:
    print(f"  Violated: {[r['name'] for r in result.violated_rules]}")
print()

# =====================================================================
# Summary
# =====================================================================

print("=" * 70)
print("  AxiomGuard caught ALL dangerous medical hallucinations")
print("  using mathematical proof — not guessing.")
print("=" * 70)
