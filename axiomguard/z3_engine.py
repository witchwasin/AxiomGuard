"""
AxiomGuard Z3 Engine — Formal Contradiction Detection via SMT Solver

v0.2.0: Assumptions API with unsat_core() for multi-claim verification.

Core idea:
  1. Assert axiom claims as background knowledge (permanent).
  2. Create tracked boolean assumptions for each response claim.
  3. One solver.check() call verifies ALL claims at once.
  4. If UNSAT → unsat_core() pinpoints exactly WHICH claims contradict.
  5. Timeout guard prevents production hanging.
"""

from __future__ import annotations

from typing import Tuple

import z3

from axiomguard.models import Claim


# Relations where a subject can only have ONE object value.
# e.g., a company can only have one location, one CEO, etc.
EXCLUSIVE_RELATIONS = frozenset({
    "location",
    "identity",
    "ceo",
    "headquarters",
    "temporal",
    "quantity",
    "ownership",
    "capital",
    "founder",
})


# =====================================================================
# v0.2.0 — Multi-Claim Verification with Assumptions API
# =====================================================================


def _claim_to_z3(
    claim: Claim,
    relation_fn: z3.FuncDeclRef,
) -> z3.ExprRef:
    """Convert a Claim to a Z3 boolean expression.

    Handles negation: if claim.negated is True, wraps in z3.Not().
    """
    expr = relation_fn(
        z3.StringVal(claim.relation),
        z3.StringVal(claim.subject),
        z3.StringVal(claim.object),
    )
    if claim.negated:
        return z3.Not(expr)
    return expr


def check_claims(
    axiom_claims: list[Claim],
    response_claims: list[Claim],
    timeout_ms: int = 2000,
) -> tuple[bool, str, list[int]]:
    """Verify response claims against axiom claims using Z3 Assumptions API.

    Pipeline:
      1. Define Relation function and uniqueness axioms.
      2. Assert all axiom claims as background knowledge.
      3. Create tracked assumptions for each response claim.
      4. Single solver.check() with all assumptions.
      5. If UNSAT → extract contradicted claim indices via unsat_core().

    Args:
        axiom_claims: Ground-truth claims (asserted permanently).
        response_claims: Claims to verify (tracked via assumptions).
        timeout_ms: Z3 solver timeout in milliseconds (default: 2000).

    Returns:
        (is_hallucinating, reason, contradicted_indices)
        - is_hallucinating: True if Z3 proves a contradiction (UNSAT).
        - reason: Human-readable explanation.
        - contradicted_indices: Indices of response_claims in the unsat core.
    """
    solver = z3.Solver()
    solver.set("timeout", timeout_ms)

    # Define the Relation function: (relation_name, subject, object) -> Bool
    StringSort = z3.StringSort()
    Relation = z3.Function(
        "Relation", StringSort, StringSort, StringSort, z3.BoolSort()
    )

    # ------------------------------------------------------------------
    # Uniqueness Axioms for exclusive relations
    # ------------------------------------------------------------------
    s = z3.Const("s", StringSort)
    o1 = z3.Const("o1", StringSort)
    o2 = z3.Const("o2", StringSort)

    for rel_name in EXCLUSIVE_RELATIONS:
        rel_val = z3.StringVal(rel_name)
        solver.add(
            z3.ForAll(
                [s, o1, o2],
                z3.Implies(
                    z3.And(Relation(rel_val, s, o1), Relation(rel_val, s, o2)),
                    o1 == o2,
                ),
            )
        )

    # ------------------------------------------------------------------
    # Assert axiom claims (background knowledge — permanent)
    # ------------------------------------------------------------------
    for ax in axiom_claims:
        solver.add(_claim_to_z3(ax, Relation))

    # ------------------------------------------------------------------
    # Create tracked assumptions for response claims
    # ------------------------------------------------------------------
    trackers: list[z3.ExprRef] = []
    tracker_map: dict[str, int] = {}  # tracker name → claim index

    for i, claim in enumerate(response_claims):
        tracker = z3.Bool(f"claim_{i}")
        trackers.append(tracker)
        tracker_map[f"claim_{i}"] = i
        solver.add(z3.Implies(tracker, _claim_to_z3(claim, Relation)))

    # ------------------------------------------------------------------
    # Check satisfiability (single call for ALL claims)
    # ------------------------------------------------------------------
    result = solver.check(*trackers)

    if result == z3.unsat:
        # Extract which response claims caused the contradiction
        core = solver.unsat_core()
        contradicted = [
            tracker_map[str(t)]
            for t in core
            if str(t) in tracker_map
        ]
        contradicted.sort()

        # Build human-readable reason
        reasons: list[str] = []
        for idx in contradicted:
            rc = response_claims[idx]
            # Find the axiom it contradicts
            for ax in axiom_claims:
                if (
                    ax.subject == rc.subject
                    and ax.relation == rc.relation
                    and ax.object != rc.object
                    and not ax.negated
                    and not rc.negated
                ):
                    reasons.append(
                        f'{rc.subject}.{rc.relation} cannot be both '
                        f'"{ax.object}" (axiom) and "{rc.object}" (response)'
                    )
                    break
            else:
                reasons.append(
                    f'claim[{idx}]: ({rc.subject}, {rc.relation}, {rc.object})'
                )

        reason_str = "; ".join(reasons) if reasons else "Z3 proved contradiction"
        return True, f"Z3 proved contradiction (UNSAT): {reason_str}", contradicted

    if result == z3.sat:
        return False, "No contradiction detected (SAT).", []

    # z3.unknown — likely timeout
    return False, f"Z3 returned unknown (possible timeout at {timeout_ms}ms).", []


# =====================================================================
# v0.1.0 — Backward Compatible Interface
# =====================================================================


def check_contradiction_z3(
    axioms_sro: list[dict],
    response_sro: dict,
) -> tuple[bool, str]:
    """Check if a response triple contradicts axiom triples (v0.1.0 compat).

    Wraps check_claims() for backward compatibility with dict-based callers.

    Args:
        axioms_sro: List of axiom dicts with keys "subject", "relation", "object".
        response_sro: Response dict with keys "subject", "relation", "object".

    Returns:
        (is_hallucinating, reason)
    """
    axiom_claims = [
        Claim(
            subject=ax["subject"],
            relation=ax["relation"],
            object=ax["object"],
            negated=ax.get("negated", False),
        )
        for ax in axioms_sro
    ]

    response_claim = Claim(
        subject=response_sro["subject"],
        relation=response_sro["relation"],
        object=response_sro["object"],
        negated=response_sro.get("negated", False),
    )

    is_hall, reason, _ = check_claims(axiom_claims, [response_claim])
    return is_hall, reason
