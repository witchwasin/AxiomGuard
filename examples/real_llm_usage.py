"""
AxiomGuard — Real LLM Backend Example
======================================

Runs the full Hybrid Verification pipeline using the Anthropic Claude API
instead of the mock keyword engine.

Requires:
    pip install anthropic
    export ANTHROPIC_API_KEY="sk-ant-..."

Run:
    python examples/real_llm_usage.py
"""

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from axiomguard import set_llm_backend, translate_to_logic, verify
from axiomguard.backends.anthropic_llm import anthropic_translator

# --- Plug in the real LLM backend ---
set_llm_backend(anthropic_translator)

# Ground-truth axioms
axioms = [
    "The company is in Bangkok",
    "The CEO is Somchai",
    "The product is AxiomGuard",
]

# Test candidates (mix of correct, paraphrase, and hallucinated)
candidates = [
    ("The company is in Bangkok", "exact match"),
    ("Our headquarters is in Bangkok", "paraphrase — should PASS"),
    ("The company is in Chiang Mai", "hallucinated location — should FAIL"),
    ("The CEO is Somchai", "exact match"),
    ("The CEO is John", "hallucinated identity — should FAIL"),
]

print("=" * 70)
print("  AxiomGuard — Real LLM Backend (Anthropic Claude)")
print("=" * 70)
print()

# Show how the LLM translates each axiom
print("--- Axiom Translations ---")
for axiom in axioms:
    triple = translate_to_logic(axiom)
    print(f"  {axiom!r}")
    print(f"    → {triple}")
print()

# Run verification on each candidate
print("--- Verification Results ---")
for text, description in candidates:
    triple = translate_to_logic(text)
    result = verify(text, axioms)

    status = "FAIL" if result.is_hallucinating else "PASS"
    print(f"  [{status}] {text!r}  ({description})")
    print(f"         Triple:  {triple}")
    if result.is_hallucinating:
        print(f"         Reason:  {result.reason}")
    print()
