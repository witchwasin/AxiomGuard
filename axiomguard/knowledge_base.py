"""
AxiomGuard Knowledge Base — Rule Compiler & Verification Engine

v0.4.0: Numeric/date sorts, selective filtering, axiom_relations().

Pipeline:
  .axiom.yml → AxiomParser → RuleSet → KnowledgeBase.add_rule() → Z3 ForAll
                                              ↓
                                     KnowledgeBase.verify()
                                              ↓
                                     VerificationResult
"""

from __future__ import annotations

from datetime import date, datetime, timezone
from itertools import combinations
from pathlib import Path
from typing import Optional, Union

import z3

from axiomguard.models import Claim, VerificationResult
from axiomguard.parser import (
    AxiomParser,
    CardinalityRule,
    ComparisonRule,
    CompositeCondition,
    CompositionRule,
    DependencyRule,
    ExclusionRule,
    NegationRule,
    RangeRule,
    RuleSet,
    TemporalRule,
    UniqueRule,
    parse_delta,
)
from axiomguard.resolver import EntityResolver
from axiomguard.z3_engine import Z3_DEFAULT_TIMEOUT_MS


# =====================================================================
# Operator helpers
# =====================================================================

_OPS = {
    "=": lambda a, b: a == b,
    "==": lambda a, b: a == b,
    "!=": lambda a, b: a != b,
    ">": lambda a, b: a > b,
    "<": lambda a, b: a < b,
    ">=": lambda a, b: a >= b,
    "<=": lambda a, b: a <= b,
}


def _parse_numeric(value: str, value_type: str) -> int | float:
    """Parse a string value into a numeric Python value."""
    if value_type == "int":
        return int(value)
    elif value_type == "float":
        return float(value)
    elif value_type == "date":
        return date.fromisoformat(value).toordinal()
    elif value_type == "datetime":
        return _parse_datetime_to_epoch(value)
    raise ValueError(f"Unknown numeric value_type: {value_type}")


def _parse_datetime_to_epoch(value: str) -> int:
    """Parse an ISO datetime string or epoch integer string to epoch seconds."""
    # Try epoch integer first (plain digits)
    if value.isdigit() or (value.startswith("-") and value[1:].isdigit()):
        return int(value)
    # Parse ISO format
    dt = datetime.fromisoformat(value)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return int(dt.timestamp())


def _resolve_system_time(
    system_time: Optional[Union[str, datetime, int]],
) -> int:
    """Convert system_time parameter to epoch seconds."""
    if system_time is None:
        return int(datetime.now(timezone.utc).timestamp())
    if isinstance(system_time, int):
        return system_time
    if isinstance(system_time, datetime):
        if system_time.tzinfo is None:
            system_time = system_time.replace(tzinfo=timezone.utc)
        return int(system_time.timestamp())
    if isinstance(system_time, str):
        return _parse_datetime_to_epoch(system_time)
    raise TypeError(f"Unsupported system_time type: {type(system_time)}")


# =====================================================================
# Knowledge Base
# =====================================================================


class KnowledgeBase:
    """Compiled rule store with Z3 verification.

    Loads .axiom.yml files, compiles rules into Z3 ForAll expressions,
    and integrates entity aliases into an EntityResolver.

    v0.4.0: Supports numeric (IntSort/RealSort) and date (ordinal day)
    attributes alongside the string-based Relation function.
    """

    def __init__(self, resolver: EntityResolver | None = None) -> None:
        self._parser = AxiomParser()
        self._resolver = resolver or EntityResolver()
        self._rulesets: list[RuleSet] = []

        # Z3 shared infrastructure — string relations
        self._StringSort = z3.StringSort()
        self._Relation = z3.Function(
            "Relation",
            self._StringSort,
            self._StringSort,
            self._StringSort,
            z3.BoolSort(),
        )

        # Z3 numeric attribute functions (v0.4.0)
        # Maps relation name → (z3.FuncDeclRef, value_type_str)
        self._numeric_attrs: dict[str, tuple[z3.FuncDeclRef, str]] = {}

        # Z3 temporal infrastructure (v0.6.0)
        self._system_time = z3.Int("system_time")
        self._has_temporal_rules = False

        # Compiled Z3 constraints
        self._constraints: list[z3.ExprRef] = []
        # Rule metadata for error messages
        self._rule_meta: list[dict] = []
        # Rule objects for violation matching
        self._loaded_rules: list = []
        # Relation classification metadata (v0.6.0)
        self._relation_categories: dict[str, str] = {}

    @property
    def resolver(self) -> EntityResolver:
        return self._resolver

    @property
    def constraint_count(self) -> int:
        return len(self._constraints)

    @property
    def rule_count(self) -> int:
        return len(self._rule_meta)

    def axiom_relations(self) -> set[str]:
        """Return all relations that have at least one rule (v0.4.0).

        Used by selective verification to skip claims whose relations
        have no matching rules — provably irrelevant, safe to skip.
        """
        rels: set[str] = set()
        for rule in self._loaded_rules:
            if isinstance(rule, UniqueRule):
                rels.add(rule.relation)
            elif isinstance(rule, ExclusionRule):
                rels.add(rule.relation)
            elif isinstance(rule, DependencyRule):
                rels.add(rule.when.relation)
                if rule.then.require:
                    rels.add(rule.then.require.relation)
                if rule.then.forbid:
                    rels.add(rule.then.forbid.relation)
                if rule.chain:
                    for step in rule.chain:
                        rels.add(step.when.relation)
                        if step.then.require:
                            rels.add(step.then.require.relation)
                        if step.then.forbid:
                            rels.add(step.then.forbid.relation)
            elif isinstance(rule, RangeRule):
                rels.add(rule.relation)
            elif isinstance(rule, NegationRule):
                rels.add(rule.relation)
            elif isinstance(rule, TemporalRule):
                rels.add(rule.relation)
                if rule.reference != "system_time":
                    rels.add(rule.reference)
            elif isinstance(rule, ComparisonRule):
                rels.add(rule.left.relation)
                rels.add(rule.right.relation)
            elif isinstance(rule, CardinalityRule):
                rels.add(rule.relation)
            elif isinstance(rule, CompositionRule):
                for group in (rule.all_of, rule.any_of, rule.none_of):
                    if group:
                        for cond in group:
                            rels.add(cond.relation)
                if rule.then.require:
                    rels.add(rule.then.require.relation)
                if rule.then.forbid:
                    rels.add(rule.then.forbid.relation)
        return rels

    # =================================================================
    # Loading
    # =================================================================

    def load(self, path: str | Path) -> RuleSet:
        ruleset = self._parser.load(path)
        self._integrate(ruleset)
        return ruleset

    def load_string(self, content: str) -> RuleSet:
        ruleset = self._parser.load_string(content)
        self._integrate(ruleset)
        return ruleset

    def _integrate(self, ruleset: RuleSet) -> None:
        self._rulesets.append(ruleset)
        for entity in ruleset.entities:
            alias_map = {alias: entity.name for alias in entity.aliases}
            self._resolver.add_aliases(alias_map)
        for rel_def in ruleset.relations:
            self._relation_categories[rel_def.name] = rel_def.category
        for rule in ruleset.rules:
            self.add_rule(rule)

    def relation_category(self, relation: str) -> str:
        """Get the classification category of a relation (v0.6.0).

        Returns "definitional", "contingent", or "normative_risk".
        Defaults to "contingent" if not declared in YAML.
        """
        return self._relation_categories.get(relation, "contingent")

    # =================================================================
    # Numeric Attribute Functions (v0.4.0)
    # =================================================================

    def _get_numeric_attr(self, relation: str, value_type: str) -> z3.FuncDeclRef:
        """Get or create a Z3 numeric function for a relation.

        Creates: attr_int_<relation>(StringSort) -> IntSort
                 attr_float_<relation>(StringSort) -> RealSort
                 attr_date_<relation>(StringSort) -> IntSort  (ordinal days)
                 attr_datetime_<relation>(StringSort) -> IntSort  (epoch seconds)
        """
        if relation in self._numeric_attrs:
            return self._numeric_attrs[relation][0]

        if value_type in ("int", "date", "datetime"):
            sort = z3.IntSort()
        elif value_type == "float":
            sort = z3.RealSort()
        else:
            raise ValueError(f"Cannot create numeric attr for value_type={value_type}")

        fn = z3.Function(f"attr_{value_type}_{relation}", self._StringSort, sort)
        self._numeric_attrs[relation] = (fn, value_type)
        return fn

    def _make_z3_val(self, value: str, value_type: str):
        """Convert a string value to the appropriate Z3 value."""
        if value_type == "int":
            return z3.IntVal(int(value))
        elif value_type == "float":
            return z3.RealVal(value)
        elif value_type == "date":
            return z3.IntVal(date.fromisoformat(value).toordinal())
        elif value_type == "datetime":
            return z3.IntVal(_parse_datetime_to_epoch(value))
        return z3.StringVal(value)

    def _apply_operator(self, lhs, operator: str, rhs):
        """Apply a comparison operator to Z3 expressions."""
        if operator not in _OPS:
            raise ValueError(f"Unknown operator: {operator}")
        return _OPS[operator](lhs, rhs)

    # =================================================================
    # Rule Compilation
    # =================================================================

    def add_rule(self, rule) -> None:
        if isinstance(rule, UniqueRule):
            constraints = self._compile_unique(rule)
        elif isinstance(rule, ExclusionRule):
            constraints = self._compile_exclusion(rule)
        elif isinstance(rule, DependencyRule):
            constraints = self._compile_dependency(rule)
        elif isinstance(rule, RangeRule):
            constraints = self._compile_range(rule)
        elif isinstance(rule, NegationRule):
            constraints = self._compile_negation(rule)
        elif isinstance(rule, TemporalRule):
            constraints = self._compile_temporal(rule)
            self._has_temporal_rules = True
        elif isinstance(rule, ComparisonRule):
            constraints = self._compile_comparison(rule)
        elif isinstance(rule, CardinalityRule):
            constraints = self._compile_cardinality(rule)
        elif isinstance(rule, CompositionRule):
            constraints = self._compile_composition(rule)
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
        """Compile dependency with optional numeric/date support (v0.4.0)."""
        R = self._Relation
        s = z3.Const("s", self._StringSort)
        o1 = z3.Const("o1", self._StringSort)
        o2 = z3.Const("o2", self._StringSort)

        # --- Build WHEN expression ---
        if rule.when.value_type != "string":
            attr_fn = self._get_numeric_attr(rule.when.relation, rule.when.value_type)
            z3_val = self._make_z3_val(rule.when.value, rule.when.value_type)
            when_expr = self._apply_operator(attr_fn(s), rule.when.operator, z3_val)
        else:
            when_rel = z3.StringVal(rule.when.relation)
            when_val = z3.StringVal(rule.when.value)
            when_expr = R(when_rel, s, when_val)

        # --- Build THEN REQUIRE expression ---
        constraints = []
        if rule.then.require is not None:
            if rule.then.require.value_type != "string":
                then_fn = self._get_numeric_attr(
                    rule.then.require.relation, rule.then.require.value_type
                )
                then_z3_val = self._make_z3_val(
                    rule.then.require.value, rule.then.require.value_type
                )
                then_expr = self._apply_operator(
                    then_fn(s), rule.then.require.operator, then_z3_val
                )
            else:
                then_rel = z3.StringVal(rule.then.require.relation)
                then_val = z3.StringVal(rule.then.require.value)
                then_expr = R(then_rel, s, then_val)

            constraints.append(
                z3.ForAll([s], z3.Implies(when_expr, then_expr)),
            )

            # Auto-uniqueness only for string-based 'then' relations
            if rule.then.require.value_type == "string":
                then_rel = z3.StringVal(rule.then.require.relation)
                constraints.append(
                    z3.ForAll(
                        [s, o1, o2],
                        z3.Implies(
                            z3.And(R(then_rel, s, o1), R(then_rel, s, o2)),
                            o1 == o2,
                        ),
                    )
                )

        # --- Build THEN FORBID expression (v0.6.0) ---
        if rule.then.forbid is not None:
            for val in rule.then.forbid.values:
                forbid_expr = z3.Not(
                    R(z3.StringVal(rule.then.forbid.relation), s, z3.StringVal(val))
                )
                constraints.append(
                    z3.ForAll([s], z3.Implies(when_expr, forbid_expr))
                )

        # --- Build CHAIN steps (v0.7.x) ---
        if rule.chain:
            for step in rule.chain:
                cw = step.when
                # Build chain WHEN expression (inherits entity from parent)
                if cw.value_type != "string":
                    chain_fn = self._get_numeric_attr(cw.relation, cw.value_type)
                    chain_val = self._make_z3_val(cw.value, cw.value_type)
                    chain_when = self._apply_operator(chain_fn(s), cw.operator, chain_val)
                else:
                    chain_when = R(z3.StringVal(cw.relation), s, z3.StringVal(cw.value))

                # Build chain THEN REQUIRE
                if step.then.require is not None:
                    ct = step.then.require
                    if ct.value_type != "string":
                        ct_fn = self._get_numeric_attr(ct.relation, ct.value_type)
                        ct_val = self._make_z3_val(ct.value, ct.value_type)
                        chain_then = self._apply_operator(ct_fn(s), ct.operator, ct_val)
                    else:
                        chain_then = R(z3.StringVal(ct.relation), s, z3.StringVal(ct.value))

                    constraints.append(
                        z3.ForAll([s], z3.Implies(chain_when, chain_then))
                    )
                    # Auto-uniqueness for string chain then
                    if ct.value_type == "string":
                        ct_rel = z3.StringVal(ct.relation)
                        constraints.append(
                            z3.ForAll(
                                [s, o1, o2],
                                z3.Implies(
                                    z3.And(R(ct_rel, s, o1), R(ct_rel, s, o2)),
                                    o1 == o2,
                                ),
                            )
                        )

                # Build chain THEN FORBID
                if step.then.forbid is not None:
                    for val in step.then.forbid.values:
                        chain_forbid = z3.Not(
                            R(z3.StringVal(step.then.forbid.relation), s, z3.StringVal(val))
                        )
                        constraints.append(
                            z3.ForAll([s], z3.Implies(chain_when, chain_forbid))
                        )

        return constraints

    def _compile_range(self, rule: RangeRule) -> list[z3.ExprRef]:
        """range → ForAll([s], And(attr(s) >= min, attr(s) <= max))"""
        attr_fn = self._get_numeric_attr(rule.relation, rule.value_type)
        s = z3.Const("s", self._StringSort)

        bounds = []
        if rule.min is not None:
            min_val = z3.IntVal(int(rule.min)) if rule.value_type == "int" else z3.RealVal(str(rule.min))
            bounds.append(attr_fn(s) >= min_val)
        if rule.max is not None:
            max_val = z3.IntVal(int(rule.max)) if rule.value_type == "int" else z3.RealVal(str(rule.max))
            bounds.append(attr_fn(s) <= max_val)

        if not bounds:
            return []

        return [z3.ForAll([s], z3.And(*bounds) if len(bounds) > 1 else bounds[0])]

    def _compile_negation(self, rule: NegationRule) -> list[z3.ExprRef]:
        """negation → ForAll([s], Not(Relation(rel, s, forbidden)))"""
        R = self._Relation
        s = z3.Const("s", self._StringSort)
        rel = z3.StringVal(rule.relation)

        constraints = []
        for forbidden in rule.must_not_include:
            constraints.append(
                z3.ForAll([s], z3.Not(R(rel, s, z3.StringVal(forbidden))))
            )
        return constraints

    def _compile_temporal(self, rule: TemporalRule) -> list[z3.ExprRef]:
        """temporal → ForAll([s], And(ref - attr(s) >= min_delta, ref - attr(s) <= max_delta))

        Reference can be 'system_time' (Z3 Int constant) or another relation
        (another datetime attribute function).
        """
        # Register the event relation as a datetime attribute
        attr_fn = self._get_numeric_attr(rule.relation, "datetime")
        s = z3.Const("s", self._StringSort)

        # Determine the reference value
        if rule.reference == "system_time":
            ref_val = self._system_time
        else:
            # Reference is another relation — register it too
            ref_fn = self._get_numeric_attr(rule.reference, "datetime")
            ref_val = ref_fn(s)

        delta_expr = ref_val - attr_fn(s)

        bounds = []
        if rule.min_delta is not None:
            min_seconds = parse_delta(rule.min_delta)
            bounds.append(delta_expr >= z3.IntVal(min_seconds))
        if rule.max_delta is not None:
            max_seconds = parse_delta(rule.max_delta)
            bounds.append(delta_expr <= z3.IntVal(max_seconds))

        if not bounds:
            return []

        constraint = z3.And(*bounds) if len(bounds) > 1 else bounds[0]
        return [z3.ForAll([s], constraint)]

    # =================================================================
    # v0.7.0 — Advanced Rule Compilation
    # =================================================================

    def _compile_comparison(self, rule: ComparisonRule) -> list[z3.ExprRef]:
        """comparison → ForAll([s], left_expr OP right_expr)

        Cross-relation arithmetic with optional multiplier.
        """
        s = z3.Const("s", self._StringSort)
        left_fn = self._get_numeric_attr(rule.left.relation, rule.left.value_type)
        right_fn = self._get_numeric_attr(rule.right.relation, rule.right.value_type)

        left_expr = left_fn(s)
        right_expr = right_fn(s)

        if rule.left.multiplier is not None:
            m = rule.left.multiplier
            left_expr = left_expr * (z3.IntVal(int(m)) if rule.left.value_type == "int" else z3.RealVal(str(m)))
        if rule.right.multiplier is not None:
            m = rule.right.multiplier
            right_expr = right_expr * (z3.IntVal(int(m)) if rule.right.value_type == "int" else z3.RealVal(str(m)))

        cmp_expr = self._apply_operator(left_expr, rule.operator, right_expr)
        return [z3.ForAll([s], cmp_expr)]

    def _compile_cardinality(self, rule: CardinalityRule) -> list[z3.ExprRef]:
        """cardinality → bounded distinct-value constraints.

        at_most N:  no (N+1) distinct values can coexist.
        at_least N: at least N distinct values must exist (modeled as
                    existence of N distinct constants).
        """
        R = self._Relation
        s = z3.Const("s", self._StringSort)
        rel = z3.StringVal(rule.relation)
        constraints = []

        if rule.at_most is not None:
            n = rule.at_most
            # Create N+1 distinct object variables
            objs = [z3.Const(f"o_card_{i}", self._StringSort) for i in range(n + 1)]
            # If all N+1 are asserted true, at least two must be equal
            all_true = z3.And(*[R(rel, s, o) for o in objs])
            some_equal = z3.Or(*[
                objs[i] == objs[j]
                for i in range(len(objs))
                for j in range(i + 1, len(objs))
            ])
            constraints.append(
                z3.ForAll([s] + objs, z3.Implies(all_true, some_equal))
            )

        if rule.at_least is not None:
            n = rule.at_least
            # Create N distinct object variables
            objs = [z3.Const(f"o_exist_{i}", self._StringSort) for i in range(n)]
            # There exist N distinct values that are all true
            all_true = z3.And(*[R(rel, s, o) for o in objs])
            all_distinct = z3.And(*[
                objs[i] != objs[j]
                for i in range(len(objs))
                for j in range(i + 1, len(objs))
            ])
            constraints.append(
                z3.ForAll([s], z3.Exists(objs, z3.And(all_true, all_distinct)))
            )

        return constraints

    def _build_condition_expr(
        self, cond: CompositeCondition, s: z3.ExprRef
    ) -> z3.ExprRef:
        """Convert a CompositeCondition to a Z3 expression."""
        if cond.value_type != "string":
            attr_fn = self._get_numeric_attr(cond.relation, cond.value_type)
            z3_val = self._make_z3_val(cond.value, cond.value_type)
            return self._apply_operator(attr_fn(s), cond.operator, z3_val)
        else:
            rel = z3.StringVal(cond.relation)
            val = z3.StringVal(cond.value)
            return self._Relation(rel, s, val)

    def _compile_composition(self, rule: CompositionRule) -> list[z3.ExprRef]:
        """composition → ForAll([s], Implies(combined_condition, then_expr))

        Combines all_of (AND), any_of (OR), none_of (NOT OR) conditions.
        """
        s = z3.Const("s", self._StringSort)
        parts = []

        if rule.all_of:
            exprs = [self._build_condition_expr(c, s) for c in rule.all_of]
            parts.append(z3.And(*exprs) if len(exprs) > 1 else exprs[0])

        if rule.any_of:
            exprs = [self._build_condition_expr(c, s) for c in rule.any_of]
            parts.append(z3.Or(*exprs) if len(exprs) > 1 else exprs[0])

        if rule.none_of:
            exprs = [self._build_condition_expr(c, s) for c in rule.none_of]
            or_expr = z3.Or(*exprs) if len(exprs) > 1 else exprs[0]
            parts.append(z3.Not(or_expr))

        when_expr = z3.And(*parts) if len(parts) > 1 else parts[0]

        # Build THEN clause
        constraints = []
        R = self._Relation

        if rule.then.require is not None:
            req = rule.then.require
            if req.value_type != "string":
                then_fn = self._get_numeric_attr(req.relation, req.value_type)
                then_val = self._make_z3_val(req.value, req.value_type)
                then_expr = self._apply_operator(then_fn(s), req.operator, then_val)
            else:
                then_expr = R(z3.StringVal(req.relation), s, z3.StringVal(req.value))
            constraints.append(z3.ForAll([s], z3.Implies(when_expr, then_expr)))

            # Auto-uniqueness for string-based 'then' relations
            if req.value_type == "string":
                o1 = z3.Const("o1", self._StringSort)
                o2 = z3.Const("o2", self._StringSort)
                then_rel = z3.StringVal(req.relation)
                constraints.append(
                    z3.ForAll(
                        [s, o1, o2],
                        z3.Implies(
                            z3.And(R(then_rel, s, o1), R(then_rel, s, o2)),
                            o1 == o2,
                        ),
                    )
                )

        if rule.then.forbid is not None:
            for val in rule.then.forbid.values:
                forbid_expr = z3.Not(
                    R(z3.StringVal(rule.then.forbid.relation), s, z3.StringVal(val))
                )
                constraints.append(z3.ForAll([s], z3.Implies(when_expr, forbid_expr)))

        return constraints

    # =================================================================
    # Verification
    # =================================================================

    def verify(
        self,
        response_claims: list[Claim],
        axiom_claims: list[Claim] | None = None,
        timeout_ms: int = Z3_DEFAULT_TIMEOUT_MS,
        system_time: Optional[Union[str, datetime, int]] = None,
    ) -> VerificationResult:
        # Resolve entities
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

        # Inject system_time for temporal rules (v0.6.0)
        if self._has_temporal_rules:
            epoch = _resolve_system_time(system_time)
            solver.add(self._system_time == z3.IntVal(epoch))

        # Assert axiom facts (ground truths + numeric attributes)
        for ax in axiom_resolved:
            self._assert_claim(solver, ax)

        # Assert response claims as tracked assumptions
        trackers: list[z3.ExprRef] = []
        tracker_map: dict[str, int] = {}

        for i, claim in enumerate(response_resolved):
            tracker = z3.Bool(f"claim_{i}")
            trackers.append(tracker)
            tracker_map[f"claim_{i}"] = i

            # Build all Z3 expressions for this claim
            exprs = self._claim_exprs(claim)
            combined = z3.And(*exprs) if len(exprs) > 1 else exprs[0]
            solver.add(z3.Implies(tracker, combined))

        # Check
        result = solver.check(*trackers)

        if result == z3.unsat:
            core = solver.unsat_core()
            contradicted = sorted([
                tracker_map[str(t)]
                for t in core
                if str(t) in tracker_map
            ])

            violated = self._match_violated_rules(
                response_resolved, axiom_resolved, contradicted
            )

            reasons = [v["message"] for v in violated if v["message"]]

            if not reasons:
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

        return VerificationResult(
            is_hallucinating=False,
            reason=f"Z3 returned unknown (possible timeout at {timeout_ms}ms).",
            confidence="uncertain",
            extraction_warnings=all_warnings,
            contradicted_claims=[],
        )

    # =================================================================
    # Claim → Z3 (with numeric support)
    # =================================================================

    def _claim_exprs(self, claim: Claim) -> list[z3.ExprRef]:
        """Convert a Claim to a list of Z3 expressions.

        Always asserts the string Relation. Additionally asserts the
        numeric attribute function if the relation has one registered.
        """
        # String relation (always)
        str_expr = self._Relation(
            z3.StringVal(claim.relation),
            z3.StringVal(claim.subject),
            z3.StringVal(claim.object),
        )
        if claim.negated:
            str_expr = z3.Not(str_expr)

        exprs = [str_expr]

        # Numeric attribute (if registered)
        if claim.relation in self._numeric_attrs:
            attr_fn, vtype = self._numeric_attrs[claim.relation]
            try:
                val = _parse_numeric(claim.object, vtype)
                if vtype in ("int", "date", "datetime"):
                    exprs.append(attr_fn(z3.StringVal(claim.subject)) == z3.IntVal(val))
                elif vtype == "float":
                    exprs.append(attr_fn(z3.StringVal(claim.subject)) == z3.RealVal(str(val)))
            except (ValueError, TypeError):
                pass  # non-parseable object — skip numeric assertion

        return exprs

    def _claim_to_z3(self, claim: Claim) -> z3.ExprRef:
        """Single Z3 expression for backward compat (string Relation only)."""
        expr = self._Relation(
            z3.StringVal(claim.relation),
            z3.StringVal(claim.subject),
            z3.StringVal(claim.object),
        )
        if claim.negated:
            return z3.Not(expr)
        return expr

    def _assert_claim(self, solver: z3.Solver, claim: Claim) -> None:
        """Assert a claim into the solver, including numeric attributes."""
        for expr in self._claim_exprs(claim):
            solver.add(expr)

    # =================================================================
    # Rule Violation Matching
    # =================================================================

    def _match_violated_rules(
        self,
        response_resolved: list[Claim],
        axiom_resolved: list[Claim],
        contradicted: list[int],
    ) -> list[dict]:
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
                    if rule.when.value_type == "string":
                        if (
                            rc.relation == rule.when.relation
                            and rc.object == rule.when.value
                        ):
                            then_met = any(
                                ax.relation == rule.then.require.relation
                                and ax.object == rule.then.require.value
                                for ax in axiom_resolved
                            )
                            if not then_met:
                                violated.append(meta)
                                seen_rules.add(meta["name"])
                    else:
                        # Numeric when — check if claim relation matches
                        if rc.relation == rule.when.relation:
                            try:
                                val = _parse_numeric(rc.object, rule.when.value_type)
                                threshold = _parse_numeric(rule.when.value, rule.when.value_type)
                                op = _OPS.get(rule.when.operator, lambda a, b: a == b)
                                if op(val, threshold):
                                    violated.append(meta)
                                    seen_rules.add(meta["name"])
                            except (ValueError, TypeError):
                                pass

                elif isinstance(rule, RangeRule):
                    if rc.relation == rule.relation:
                        try:
                            val = _parse_numeric(rc.object, rule.value_type)
                            if rule.min is not None and val < rule.min:
                                violated.append(meta)
                                seen_rules.add(meta["name"])
                            elif rule.max is not None and val > rule.max:
                                violated.append(meta)
                                seen_rules.add(meta["name"])
                        except (ValueError, TypeError):
                            pass

                elif isinstance(rule, NegationRule):
                    if rc.relation == rule.relation and rc.object in rule.must_not_include:
                        violated.append(meta)
                        seen_rules.add(meta["name"])

                elif isinstance(rule, TemporalRule):
                    if rc.relation == rule.relation or (
                        rule.reference != "system_time"
                        and rc.relation == rule.reference
                    ):
                        violated.append(meta)
                        seen_rules.add(meta["name"])

                elif isinstance(rule, ComparisonRule):
                    if rc.relation in (rule.left.relation, rule.right.relation):
                        violated.append(meta)
                        seen_rules.add(meta["name"])

                elif isinstance(rule, CardinalityRule):
                    if rc.relation == rule.relation:
                        violated.append(meta)
                        seen_rules.add(meta["name"])

                elif isinstance(rule, CompositionRule):
                    # Match if claim touches any condition or then relation
                    rels = set()
                    for group in (rule.all_of, rule.any_of, rule.none_of):
                        if group:
                            for cond in group:
                                rels.add(cond.relation)
                    if rule.then.require:
                        rels.add(rule.then.require.relation)
                    if rule.then.forbid:
                        rels.add(rule.then.forbid.relation)
                    if rc.relation in rels:
                        violated.append(meta)
                        seen_rules.add(meta["name"])

        return violated

    # =================================================================
    # Inline Example Runner
    # =================================================================

    def run_examples(self) -> tuple[int, int, list[str]]:
        from axiomguard.core import _extract

        passed = 0
        total = 0
        failures: list[str] = []

        for ruleset in self._rulesets:
            for rule in ruleset.rules:
                for example in rule.examples:
                    total += 1
                    response_claims = _extract(example.input)
                    axiom_claims: list[Claim] = []
                    for axiom_text in example.axioms:
                        axiom_claims.extend(_extract(axiom_text))

                    result = self.verify(response_claims, axiom_claims)

                    if (example.expect == "fail") == result.is_hallucinating:
                        passed += 1
                    else:
                        failures.append(
                            f'Rule "{rule.name}" example: '
                            f'input="{example.input}", '
                            f'expected={example.expect}, '
                            f'got={"fail" if result.is_hallucinating else "pass"}'
                        )

        return passed, total, failures
