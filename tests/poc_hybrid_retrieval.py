"""
AxiomGuard — Proof of Concept: Hybrid Retrieval Filter
=======================================================

Goal:
  Prove that a lightweight deterministic logic layer can override vector
  similarity when semantically-close documents are logically contradictory,
  WITHOUT touching the embedding model weights.

Scenario:
  Axiom (ground truth): "The company is in Bangkok"

  Candidates:
    A: "The company is in Bangkok"          — correct, high similarity
    B: "Our headquarters is in Bangkok"     — correct, synonym/paraphrase
    C: "The company is in Chiang Mai"       — WRONG, but high similarity!

  In standard RAG, C ranks as high as A because the sentence structures
  are nearly identical. Our logic filter must detect the contradiction
  and kick C out of the results.

Pipeline:
  1. Compute cosine similarity (simulated embedding scores)
  2. Compute logic contradiction score (AxiomGuard engine)
  3. Combine into a hybrid score:  hybrid = sim * (1 - penalty)
  4. Re-rank — C must drop below B

Run:
  python tests/poc_hybrid_retrieval.py
"""

import math
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from axiomguard.core import verify


# =====================================================================
# Step 1: Simulated Semantic Similarity (ML Layer)
# =====================================================================
# In production these come from an embedding model (e.g. text-embedding-3).
# We hardcode realistic cosine-similarity values that illustrate the problem.

SIMULATED_COSINE_SIMILARITY = {
    "A": 1.00,   # exact match with axiom
    "B": 0.87,   # paraphrase — lower because different words
    "C": 0.96,   # contradictory — but almost identical structure!
}

CANDIDATES = {
    "A": "The company is in Bangkok",
    "B": "Our headquarters is in Bangkok",
    "C": "The company is in Chiang Mai",
}

AXIOMS = [
    "The company is in Bangkok",
]


# =====================================================================
# Step 2: Logic Contradiction Score (Deterministic Layer)
# =====================================================================
# Uses AxiomGuard's verify() to produce a binary contradiction flag.
# In v0.1+ this will be backed by Z3; for now the keyword engine suffices.

def compute_contradiction_score(candidate: str, axioms: list[str]) -> float:
    """Return 1.0 if contradicted, 0.0 if consistent."""
    result = verify(candidate, axioms)
    return 1.0 if result.is_hallucinating else 0.0


# =====================================================================
# Step 3: Hybrid Scoring Function
# =====================================================================
# The core equation:
#
#   hybrid_score = cosine_sim × (1 - λ · contradiction)
#
# Where:
#   cosine_sim    ∈ [0, 1]  — from the embedding model (untouched)
#   contradiction ∈ {0, 1}  — from the logic engine
#   λ             ∈ [0, 1]  — penalty weight (1.0 = full veto)
#
# When contradiction = 1 and λ = 1.0:
#   hybrid_score = cosine_sim × 0 = 0  → effectively filtered out
#
# This NEVER modifies the embedding. It only adjusts the ranking score.

LAMBDA = 1.0  # full penalty — zero tolerance for contradiction


def hybrid_score(cosine_sim: float, contradiction: float) -> float:
    return cosine_sim * (1.0 - LAMBDA * contradiction)


# =====================================================================
# Step 4: Run the PoC
# =====================================================================

def main():
    print("=" * 64)
    print("  AxiomGuard PoC — Hybrid Retrieval Filter")
    print("=" * 64)
    print()
    print(f"  Axiom: {AXIOMS[0]!r}")
    print()

    # --- Standard RAG ranking (vector only) ---
    print("-" * 64)
    print("  STANDARD RAG (Vector Similarity Only)")
    print("-" * 64)

    standard_ranking = sorted(
        SIMULATED_COSINE_SIMILARITY.items(),
        key=lambda x: x[1],
        reverse=True,
    )

    for rank, (label, sim) in enumerate(standard_ranking, 1):
        marker = " ← WRONG!" if label == "C" else ""
        print(f"  #{rank}  [{label}] sim={sim:.2f}  {CANDIDATES[label]!r}{marker}")

    print()
    print("  Problem: C ranks #2 despite being logically wrong.")
    print()

    # --- AxiomGuard hybrid ranking ---
    print("-" * 64)
    print("  AXIOMGUARD HYBRID (Vector + Logic Filter)")
    print("-" * 64)

    results = []
    for label, text in CANDIDATES.items():
        sim = SIMULATED_COSINE_SIMILARITY[label]
        contradiction = compute_contradiction_score(text, AXIOMS)
        h_score = hybrid_score(sim, contradiction)
        verification = verify(text, AXIOMS)

        results.append({
            "label": label,
            "text": text,
            "cosine_sim": sim,
            "contradiction": contradiction,
            "hybrid_score": h_score,
            "reason": verification.reason,
        })

    # Sort by hybrid score descending
    results.sort(key=lambda x: x["hybrid_score"], reverse=True)

    for rank, r in enumerate(results, 1):
        status = "PASS" if r["contradiction"] == 0.0 else "BLOCKED"
        print(f"  #{rank}  [{r['label']}]  sim={r['cosine_sim']:.2f}"
              f"  logic={status:<7s}"
              f"  hybrid={r['hybrid_score']:.2f}"
              f"  {r['text']!r}")
        if r["contradiction"] == 1.0:
            print(f"       Reason: {r['reason']}")

    print()

    # --- Verification: did C get kicked out? ---
    top_labels = [r["label"] for r in results if r["hybrid_score"] > 0]
    c_blocked = results[-1]["label"] == "C" and results[-1]["hybrid_score"] == 0.0
    b_promoted = any(
        r["label"] == "B" and r["hybrid_score"] > 0 for r in results
    )

    print("=" * 64)
    print("  RESULT")
    print("=" * 64)

    if c_blocked and b_promoted:
        print("  [PASS] C was blocked by logic filter (hybrid_score = 0.00)")
        print("  [PASS] B was promoted as the correct paraphrase")
        print()
        print("  Conclusion: The hybrid equation works.")
        print("  The embedding was NEVER modified — only the ranking score.")
    else:
        print("  [FAIL] The filter did not work as expected.")
        sys.exit(1)

    print()


if __name__ == "__main__":
    main()
