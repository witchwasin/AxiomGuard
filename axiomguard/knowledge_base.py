"""
AxiomGuard Knowledge Base — Rule Compiler & Verification Engine

Translates declarative YAML rules into Z3 ForAll expressions and provides
a verify() method that uses the compiled rules as background knowledge.

Pipeline:
  .axiom.yml → AxiomParser → RuleSet → KnowledgeBase.add_rule() → Z3 ForAll
                                              ↓
                                     KnowledgeBase.verify()
                                              ↓
                                     VerificationResult

Usage:
    from axiomguard.knowledge_base import KnowledgeBase

    kb = KnowledgeBase()
    kb.load("rules/medical.axiom.yml")
    result = kb.verify(response_claims, axiom_claims)
"""

from __future__ import annotations

from itertools import combinations
from pathlib import Path
from typing import List

import z3

from axiomguard.models import Claim, VerificationResult
from axiomguard.parser import (
    AxiomParser,
    DependencyRule,
    ExclusionRule,
    RuleSet,
    UniqueRule,
)
from axiomguard.resolver import EntityResolver


# =====================================================================
# Knowledge Base
# =====================================================================


class KnowledgeBase:
    """Compiled rule store with Z3 verification.

    Loads .axiom.yml files, compiles rules into Z3 ForAll expressions,
    and integrates entity aliases into an EntityResolver.

    Example::

        kb = KnowledgeBase()
        kb.load("rules/medical.axiom.yml")

        result = kb.verify(
            response_claims=[Claim(subject="patient", relation="takes", object="Aspirin")],
            axiom_claims=[Claim(subject="patient", relation="takes", object="Warfarin")],
        )
        print(result.is_hallucinating)  # True — drug interaction
    """

    def __init__(self, resolver: EntityResolver | None = None) -> None:
        self._parser = AxiomParser()
        self._resolver = resolver or EntityResolver()
        self._rulesets: list[RuleSet] = []

        # Z3 shared infrastructure
        self._StringSort = z3.StringSort()
        self._Relation = z3.Function(
            "Relation",
            self._StringSort,
            self._StringSort,
            self._StringSort,
            z3.BoolSort(),
        )

        # Compiled Z3 constraints (ForAll expressions)
        self._constraints: list[z3.ExprRef] = []
        # Rule metadata for error messages
        self._rule_meta: list[dict] = []
        # Rule objects for violation matching
        self._loaded_rules: list = []

    @property
    def resolver(self) -> EntityResolver:
        """The EntityResolver used by this KnowledgeBase."""
        return self._resolver

    @property
    def constraint_count(self) -> int:
        """Number of compiled Z3 constraints."""
        return len(self._constraints)

    @property
    def rule_count(self) -> int:
        """Number of loaded rules."""
        return len(self._rule_meta)

    # =================================================================
    # Loading
    # =================================================================

    def load(self, path: str | Path) -> RuleSet:
        """Load an .axiom.yml file: parse, validate, compile, and integrate.

        Args:
            path: Path to the .axiom.yml file.

        Returns:
            The parsed RuleSet (for inspection).
        """
        ruleset = self._parser.load(path)
        self._integrate(ruleset)
        return ruleset

    def load_string(self, content: str) -> RuleSet:
        """Load from a YAML string (useful for testing).

        Args:
            content: YAML content.

        Returns:
            The parsed RuleSet.
        """
        ruleset = self._parser.load_string(content)
        self._integrate(ruleset)
        return ruleset

    def _integrate(self, ruleset: RuleSet) -> None:
        """Integrate a parsed RuleSet: compile rules + merge entities."""
        self._rulesets.append(ruleset)

        # Merge entity aliases into resolver
        for entity in ruleset.entities:
            alias_map = {alias: entity.name for alias in entity.aliases}
            self._resolver.add_aliases(alias_map)

        # Compile each rule
        for rule in ruleset.rules:
            self.add_rule(rule)

    # =================================================================
    # Rule Compilation
    # =================================================================

    def add_rule(self, rule: UniqueRule | ExclusionRule | DependencyRule) -> None:
        """Compile a single rule into Z3 constraints and store it.

        Args:
            rule: A validated rule object from the parser.
        """
        if isinstance(rule, UniqueRule):
            constraints = self._compile_unique(rule)
        elif isinstance(rule, ExclusionRule):
            constraints = self._compile_exclusion(rule)
        elif isinstance(rule, DependencyRule):
            constraints = self._compile_dependency(rule)
        else:
            raise ValueError(f"Unknown rule type: {type(rule)}")

        self._constraints.extend(constraints)
        meta = {
            "name": rule.name,
            "type": rule.type,
            "severity": rule.severity,
            "message": rule.message,
        }
        self._rule_meta.append(meta)
        self._loaded_rules.append(rule)

    def _compile_unique(self, rule: UniqueRule) -> list[z3.ExprRef]:
        """unique → ForAll([s, o1, o2], Implies(And(R(rel,s,o1), R(rel,s,o2)), o1 == o2))"""
        R = self._Relation
        s = z3.Const("s", self._StringSort)
        o1 = z3.Const("o1", self._StringSort)
        o2 = z3.Const("o2", self._StringSort)
        rel = z3.StringVal(rule.relation)

        return [
            z3.ForAll(
                [s, o1, o2],
                z3.Implies(
                    z3.And(R(rel, s, o1), R(rel, s, o2)),
                    o1 == o2,
                ),
            )
        ]

    def _compile_exclusion(self, rule: ExclusionRule) -> list[z3.ExprRef]:
        """exclusion → ForAll([s], Not(And(R(rel,s,v1), R(rel,s,v2)))) for all pairs"""
        R = self._Relation
        s = z3.Const("s", self._StringSort)
        rel = z3.StringVal(rule.relation)

        constraints = []
        for v1, v2 in combinations(rule.values, 2):
            constraints.append(
                z3.ForAll(
                    [s],
                    z3.Not(
                        z3.And(
                            R(rel, s, z3.StringVal(v1)),
                            R(rel, s, z3.StringVal(v2)),
                        )
                    ),
                )
            )
        return constraints

    def _compile_dependency(self, rule: DependencyRule) -> list[z3.ExprRef]:
        """dependency → Implies + auto-uniqueness on the 'then' relation.

        The implication alone is not enough: if the 'then' relation is not
        exclusive, Z3 allows both the required value AND a different value
        to coexist (SAT). We add a uniqueness constraint on the 'then'
        relation so that conflicting values cause UNSAT.
        """
        R = self._Relation
        s = z3.Const("s", self._StringSort)
        o1 = z3.Const("o1", self._StringSort)
        o2 = z3.Const("o2", self._StringSort)

        when_rel = z3.StringVal(rule.when.relation)
        when_val = z3.StringVal(rule.when.value)
        then_rel = z3.StringVal(rule.then.require.relation)
        then_val = z3.StringVal(rule.then.require.value)

        return [
            # The implication: if when-condition, then requirement
            z3.ForAll(
                [s],
                z3.Implies(
                    R(when_rel, s, when_val),
                    R(then_rel, s, then_val),
                ),
            ),
            # Auto-uniqueness on the 'then' relation: one value per entity
            z3.ForAll(
                [s, o1, o2],
                z3.Implies(
                    z3.And(R(then_rel, s, o1), R(then_rel, s, o2)),
                    o1 == o2,
                ),
            ),
        ]

    # =================================================================
    # Verification
    # =================================================================

    def verify(
        self,
        response_claims: list[Claim],
        axiom_claims: list[Claim] | None = None,
        timeout_ms: int = 2000,
    ) -> VerificationResult:
        """Verify response claims against compiled rules and optional axiom facts.

        Pipeline:
          1. Create solver with timeout.
          2. Add compiled YAML rules (ForAll constraints).
          3. Assert axiom claims as background facts.
          4. Create tracked assumptions for response claims.
          5. Check satisfiability → VerificationResult.

        Args:
            response_claims: Claims to verify (tracked via assumptions).
            axiom_claims: Optional ground-truth facts.
            timeout_ms: Z3 solver timeout (default: 2000ms).

        Returns:
            VerificationResult with confidence, reason, and contradicted_claims.
        """
        # Resolve entities in all claims
        response_resolved, resp_warnings = self._resolver.resolve_claims(response_claims)
        axiom_resolved = []
        ax_warnings: list[str] = []
        if axiom_claims:
            axiom_resolved, ax_warnings = self._resolver.resolve_claims(axiom_claims)

        all_warnings = ax_warnings + resp_warnings

        # Build solver
        solver = z3.Solver()
        solver.set("timeout", timeout_ms)

        # Add compiled rules (ForAll constraints from YAML)
        for constraint in self._constraints:
            solver.add(constraint)

        # Add axiom facts (ground truths)
        for ax in axiom_resolved:
            solver.add(self._claim_to_z3(ax))

        # Add response claims as tracked assumptions
        trackers: list[z3.ExprRef] = []
        tracker_map: dict[str, int] = {}

        for i, claim in enumerate(response_resolved):
            tracker = z3.Bool(f"claim_{i}")
            trackers.append(tracker)
            tracker_map[f"claim_{i}"] = i
            solver.add(z3.Implies(tracker, self._claim_to_z3(claim)))

        # Check
        result = solver.check(*trackers)

        if result == z3.unsat:
            core = solver.unsat_core()
            contradicted = sorted([
                tracker_map[str(t)]
                for t in core
                if str(t) in tracker_map
            ])

            # Match contradicted claims to YAML rules
            violated = self._match_violated_rules(
                response_resolved, axiom_resolved, contradicted
            )

            # Build reason: prefer custom YAML messages, fallback to Z3 detail
            reasons = []
            for v in violated:
                if v["message"]:
                    reasons.append(v["message"])

            if not reasons:
                # Fallback: build from claim data
                for idx in contradicted:
                    rc = response_resolved[idx]
                    for ax in axiom_resolved:
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
                            f'claim[{idx}] ({rc.subject}, {rc.relation}, {rc.object}) '
                            f'violates rule constraints'
                        )

            reason_str = "; ".join(reasons) if reasons else "Z3 proved contradiction"

            return VerificationResult(
                is_hallucinating=True,
                reason=f"Z3 proved contradiction (UNSAT): {reason_str}",
                confidence="proven",
                extraction_warnings=all_warnings,
                contradicted_claims=contradicted,
                violated_rules=violated,
            )

        if result == z3.sat:
            confidence = "uncertain" if all_warnings else "proven"
            return VerificationResult(
                is_hallucinating=False,
                reason="No contradiction detected (SAT).",
                confidence=confidence,
                extraction_warnings=all_warnings,
                contradicted_claims=[],
            )

        # z3.unknown — likely timeout
        return VerificationResult(
            is_hallucinating=False,
            reason=f"Z3 returned unknown (possible timeout at {timeout_ms}ms).",
            confidence="uncertain",
            extraction_warnings=all_warnings,
            contradicted_claims=[],
        )

    def _match_violated_rules(
        self,
        response_resolved: list[Claim],
        axiom_resolved: list[Claim],
        contradicted: list[int],
    ) -> list[dict]:
        """Match contradicted claims to the YAML rules they violated.

        Examines each contradicted response claim and checks which loaded
        rules apply based on relation and values.

        Returns:
            List of rule metadata dicts (name, type, severity, message).
            Deduplicated — each rule appears at most once.
        """
        violated: list[dict] = []
        seen_rules: set[str] = set()

        for idx in contradicted:
            rc = response_resolved[idx]

            for rule, meta in zip(self._loaded_rules, self._rule_meta):
                if meta["name"] in seen_rules:
                    continue

                if isinstance(rule, UniqueRule):
                    if rc.relation == rule.relation:
                        for ax in axiom_resolved:
                            if (
                                ax.subject == rc.subject
                                and ax.relation == rule.relation
                                and ax.object != rc.object
                            ):
                                violated.append(meta)
                                seen_rules.add(meta["name"])
                                break

                elif isinstance(rule, ExclusionRule):
                    if rc.relation == rule.relation and rc.object in rule.values:
                        for ax in axiom_resolved:
                            if (
                                ax.relation == rule.relation
                                and ax.object in rule.values
                                and ax.object != rc.object
                            ):
                                violated.append(meta)
                                seen_rules.add(meta["name"])
                                break

                elif isinstance(rule, DependencyRule):
                    if (
                        rc.relation == rule.when.relation
                        and rc.object == rule.when.value
                    ):
                        # Check that the 'then' requirement is NOT met
                        then_met = any(
                            ax.relation == rule.then.require.relation
                            and ax.object == rule.then.require.value
                            for ax in axiom_resolved
                        )
                        if not then_met:
                            violated.append(meta)
                            seen_rules.add(meta["name"])

        return violated

    def _claim_to_z3(self, claim: Claim) -> z3.ExprRef:
        """Convert a Claim to a Z3 expression using this KB's Relation function."""
        expr = self._Relation(
            z3.StringVal(claim.relation),
            z3.StringVal(claim.subject),
            z3.StringVal(claim.object),
        )
        if claim.negated:
            return z3.Not(expr)
        return expr

    # =================================================================
    # Inline Example Runner
    # =================================================================

    def run_examples(self) -> tuple[int, int, list[str]]:
        """Run all inline test examples from loaded rules.

        Returns:
            (passed, total, failures) where failures is a list of error messages.
        """
        from axiomguard.core import _extract

        passed = 0
        total = 0
        failures: list[str] = []

        for ruleset in self._rulesets:
            for rule in ruleset.rules:
                for example in rule.examples:
                    total += 1

                    # Extract claims from input and axioms
                    response_claims = _extract(example.input)
                    axiom_claims: list[Claim] = []
                    for axiom_text in example.axioms:
                        axiom_claims.extend(_extract(axiom_text))

                    result = self.verify(response_claims, axiom_claims)

                    expected_fail = example.expect == "fail"
                    actual_fail = result.is_hallucinating

                    if expected_fail == actual_fail:
                        passed += 1
                    else:
                        failures.append(
                            f'Rule "{rule.name}" example: '
                            f'input="{example.input}", '
                            f'expected={example.expect}, '
                            f'got={"fail" if actual_fail else "pass"}'
                        )

        return passed, total, failures
