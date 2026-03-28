"""
AxiomGuard Z3 Engine — Formal Contradiction Detection via SMT Solver

Uses the Z3 theorem prover to mathematically verify whether a response's
SRO triple contradicts a set of axiom SRO triples.

Core idea:
  1. Model each SRO triple as a relation: Relation(relation_name, subject, object)
  2. Add a Uniqueness Axiom for exclusive relations: a given (relation, subject)
     pair can map to at most ONE object.
  3. Assert all axiom triples and the response triple.
  4. If the solver returns UNSAT → proven contradiction → hallucination.
"""

from __future__ import annotations

import z3

# Relations where a subject can only have ONE object value.
# e.g., a company can only have one location, one CEO, etc.
EXCLUSIVE_RELATIONS = {
    "location",
    "identity",
    "ceo",
    "headquarters",
    "temporal",
    "quantity",
    "ownership",
}


def check_contradiction_z3(
    axioms_sro: list[dict],
    response_sro: dict,
) -> tuple[bool, str]:
    """Check if a response triple contradicts axiom triples using Z3.

    Args:
        axioms_sro: List of axiom dicts with keys "subject", "relation", "object".
        response_sro: Response dict with keys "subject", "relation", "object".

    Returns:
        (True, reason) if Z3 proves a contradiction (UNSAT).
        (False, reason) if no contradiction found (SAT or UNKNOWN).
    """
    solver = z3.Solver()

    # Define the Relation function: (relation_name, subject, object) -> Bool
    StringSort = z3.StringSort()
    Relation = z3.Function("Relation", StringSort, StringSort, StringSort, z3.BoolSort())

    # ------------------------------------------------------------------
    # Uniqueness Axiom (for exclusive relations):
    #   ForAll([r, s, o1, o2],
    #       Implies(And(Relation(r, s, o1), Relation(r, s, o2)), o1 == o2))
    #
    # This means: if a relation is asserted for the same (relation, subject)
    # with two different objects, it's a contradiction.
    # ------------------------------------------------------------------
    s = z3.Const("s", StringSort)
    o1 = z3.Const("o1", StringSort)
    o2 = z3.Const("o2", StringSort)

    # Apply uniqueness only to exclusive relations
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
    # Assert axiom triples
    # ------------------------------------------------------------------
    for ax in axioms_sro:
        solver.add(
            Relation(
                z3.StringVal(ax["relation"]),
                z3.StringVal(ax["subject"]),
                z3.StringVal(ax["object"]),
            )
        )

    # ------------------------------------------------------------------
    # Assert response triple
    # ------------------------------------------------------------------
    solver.add(
        Relation(
            z3.StringVal(response_sro["relation"]),
            z3.StringVal(response_sro["subject"]),
            z3.StringVal(response_sro["object"]),
        )
    )

    # ------------------------------------------------------------------
    # Check satisfiability
    # ------------------------------------------------------------------
    result = solver.check()

    if result == z3.unsat:
        # Find which axiom was contradicted for the reason message
        r_rel = response_sro["relation"]
        r_subj = response_sro["subject"]
        r_obj = response_sro["object"]

        for ax in axioms_sro:
            if ax["subject"] == r_subj and ax["relation"] == r_rel and ax["object"] != r_obj:
                return True, (
                    f'Z3 proved contradiction (UNSAT): '
                    f'{r_subj}.{r_rel} cannot be both '
                    f'"{ax["object"]}" (axiom) and "{r_obj}" (response)'
                )

        return True, "Z3 proved a contradiction: UNSAT"

    if result == z3.sat:
        return False, "No contradiction detected (SAT)."

    # z3.unknown
    return False, "Z3 returned unknown — no contradiction proven."
