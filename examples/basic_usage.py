import sys
import os

# Allow running from the repo root: python examples/basic_usage.py
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from axiomguard import verify

# Ground-truth axioms
axioms = [
    "The company is in Bangkok",
    "The CEO is Somchai",
    "The product is AxiomGuard",
]

# --- Test 1: Hallucinated response ---
hallucinated = "The company is in Chiang Mai"
result = verify(hallucinated, axioms)
print(f"Response: {hallucinated!r}")
print(f"Result:   {result}")
print()

# --- Test 2: Truthful response ---
truthful = "The company is in Bangkok"
result = verify(truthful, axioms)
print(f"Response: {truthful!r}")
print(f"Result:   {result}")
