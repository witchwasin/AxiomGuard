"""
Tests for v0.7.0 — Advanced Rule Types.

Covers: ComparisonRule, CardinalityRule, CompositionRule.
"""

import pytest

from axiomguard import KnowledgeBase, Claim
from axiomguard.parser import (
    AxiomParser,
    CardinalityRule,
    ComparisonRule,
    CompositionRule,
)


# =====================================================================
# ComparisonRule — cross-relation arithmetic
# =====================================================================


class TestComparisonParsing:

    def test_parse_basic_comparison(self):
        parser = AxiomParser()
        rs = parser.load_string("""
axiomguard: "0.7"
domain: test
rules:
  - name: loan_ratio
    type: comparison
    entity: applicant
    left:
      relation: loan_amount
      value_type: int
    operator: "<="
    right:
      relation: salary
      multiplier: 5
      value_type: int
    message: "Loan must not exceed 5x salary."
""")
        rule = rs.rules[0]
        assert isinstance(rule, ComparisonRule)
        assert rule.left.relation == "loan_amount"
        assert rule.right.multiplier == 5
        assert rule.operator == "<="

    def test_parse_no_multiplier(self):
        parser = AxiomParser()
        rs = parser.load_string("""
axiomguard: "0.7"
domain: test
rules:
  - name: balance_check
    type: comparison
    entity: account
    left:
      relation: debit
      value_type: int
    operator: "<="
    right:
      relation: credit
      value_type: int
    message: "Debit must not exceed credit."
""")
        rule = rs.rules[0]
        assert rule.left.multiplier is None
        assert rule.right.multiplier is None


class TestComparisonVerification:

    def _kb_loan_ratio(self) -> KnowledgeBase:
        kb = KnowledgeBase()
        kb.load_string("""
axiomguard: "0.7"
domain: test
rules:
  - name: loan_ratio
    type: comparison
    entity: applicant
    left:
      relation: loan_amount
      value_type: int
    operator: "<="
    right:
      relation: salary
      multiplier: 5
      value_type: int
    message: "Loan must not exceed 5x salary."
""")
        return kb

    def test_within_ratio_passes(self):
        kb = self._kb_loan_ratio()
        r = kb.verify(response_claims=[
            Claim(subject="applicant", relation="loan_amount", object="100000"),
            Claim(subject="applicant", relation="salary", object="30000"),
        ])
        assert not r.is_hallucinating

    def test_exceeds_ratio_fails(self):
        kb = self._kb_loan_ratio()
        r = kb.verify(response_claims=[
            Claim(subject="applicant", relation="loan_amount", object="200000"),
            Claim(subject="applicant", relation="salary", object="30000"),
        ])
        assert r.is_hallucinating

    def test_exact_boundary_passes(self):
        kb = self._kb_loan_ratio()
        r = kb.verify(response_claims=[
            Claim(subject="applicant", relation="loan_amount", object="150000"),
            Claim(subject="applicant", relation="salary", object="30000"),
        ])
        assert not r.is_hallucinating

    def test_violated_rules_has_message(self):
        kb = self._kb_loan_ratio()
        r = kb.verify(response_claims=[
            Claim(subject="applicant", relation="loan_amount", object="999999"),
            Claim(subject="applicant", relation="salary", object="10000"),
        ])
        assert r.is_hallucinating
        assert any("5x salary" in v["message"] for v in r.violated_rules)

    def test_simple_comparison_no_multiplier(self):
        kb = KnowledgeBase()
        kb.load_string("""
axiomguard: "0.7"
domain: test
rules:
  - name: debit_credit
    type: comparison
    entity: account
    left:
      relation: debit
      value_type: int
    operator: "<="
    right:
      relation: credit
      value_type: int
    message: "Debit must not exceed credit."
""")
        # debit=50, credit=100 → OK
        r = kb.verify(response_claims=[
            Claim(subject="account", relation="debit", object="50"),
            Claim(subject="account", relation="credit", object="100"),
        ])
        assert not r.is_hallucinating

        # debit=150, credit=100 → FAIL
        r2 = kb.verify(response_claims=[
            Claim(subject="account", relation="debit", object="150"),
            Claim(subject="account", relation="credit", object="100"),
        ])
        assert r2.is_hallucinating


# =====================================================================
# CardinalityRule — at_most / at_least
# =====================================================================


class TestCardinalityParsing:

    def test_parse_at_most(self):
        parser = AxiomParser()
        rs = parser.load_string("""
axiomguard: "0.7"
domain: test
rules:
  - name: max_diagnoses
    type: cardinality
    entity: patient
    relation: primary_diagnosis
    at_most: 2
    message: "Max 2 primary diagnoses."
""")
        rule = rs.rules[0]
        assert isinstance(rule, CardinalityRule)
        assert rule.at_most == 2
        assert rule.at_least is None

    def test_parse_at_least(self):
        parser = AxiomParser()
        rs = parser.load_string("""
axiomguard: "0.7"
domain: test
rules:
  - name: emergency_contact
    type: cardinality
    entity: employee
    relation: emergency_contact
    at_least: 1
    message: "At least 1 emergency contact."
""")
        rule = rs.rules[0]
        assert rule.at_least == 1

    def test_no_bound_raises(self):
        parser = AxiomParser()
        with pytest.raises(Exception):
            parser.load_string("""
axiomguard: "0.7"
domain: test
rules:
  - name: bad_rule
    type: cardinality
    entity: patient
    relation: diagnosis
    message: "No bound specified."
""")


class TestCardinalityVerification:

    def test_at_most_within_limit(self):
        """2 diagnoses with at_most=2 → should pass."""
        kb = KnowledgeBase()
        kb.load_string("""
axiomguard: "0.7"
domain: test
rules:
  - name: max_diagnoses
    type: cardinality
    entity: patient
    relation: primary_diagnosis
    at_most: 2
    message: "Max 2 primary diagnoses."
""")
        r = kb.verify(response_claims=[
            Claim(subject="patient", relation="primary_diagnosis", object="flu"),
            Claim(subject="patient", relation="primary_diagnosis", object="cold"),
        ])
        assert not r.is_hallucinating

    def test_at_most_exceeds_limit(self):
        """3 diagnoses with at_most=2 → should fail."""
        kb = KnowledgeBase()
        kb.load_string("""
axiomguard: "0.7"
domain: test
rules:
  - name: max_diagnoses
    type: cardinality
    entity: patient
    relation: primary_diagnosis
    at_most: 2
    message: "Max 2 primary diagnoses."
""")
        r = kb.verify(response_claims=[
            Claim(subject="patient", relation="primary_diagnosis", object="flu"),
            Claim(subject="patient", relation="primary_diagnosis", object="cold"),
            Claim(subject="patient", relation="primary_diagnosis", object="covid"),
        ])
        assert r.is_hallucinating


# =====================================================================
# CompositionRule — AND/OR/NOT logic
# =====================================================================


class TestCompositionParsing:

    def test_parse_all_of(self):
        parser = AxiomParser()
        rs = parser.load_string("""
axiomguard: "0.7"
domain: test
rules:
  - name: elderly_diabetic
    type: composition
    all_of:
      - entity: patient
        relation: age
        operator: ">"
        value: "60"
        value_type: int
      - entity: patient
        relation: condition
        value: diabetes
    then:
      require:
        relation: annual_checkup
        value: required
    message: "Elderly diabetics need checkups."
""")
        rule = rs.rules[0]
        assert isinstance(rule, CompositionRule)
        assert len(rule.all_of) == 2
        assert rule.then.require.value == "required"

    def test_parse_any_of(self):
        parser = AxiomParser()
        rs = parser.load_string("""
axiomguard: "0.7"
domain: test
rules:
  - name: high_risk
    type: composition
    any_of:
      - entity: patient
        relation: condition
        value: heart_disease
      - entity: patient
        relation: condition
        value: diabetes
    then:
      require:
        relation: risk_level
        value: high
    message: "High risk patient."
""")
        rule = rs.rules[0]
        assert rule.any_of is not None
        assert len(rule.any_of) == 2

    def test_no_group_raises(self):
        parser = AxiomParser()
        with pytest.raises(Exception):
            parser.load_string("""
axiomguard: "0.7"
domain: test
rules:
  - name: bad_rule
    type: composition
    then:
      require:
        relation: foo
        value: bar
    message: "No conditions."
""")


class TestCompositionVerification:

    def _kb_elderly_diabetic(self) -> KnowledgeBase:
        kb = KnowledgeBase()
        kb.load_string("""
axiomguard: "0.7"
domain: test
rules:
  - name: elderly_diabetic
    type: composition
    all_of:
      - entity: patient
        relation: age
        operator: ">"
        value: "60"
        value_type: int
      - entity: patient
        relation: condition
        value: diabetes
    then:
      require:
        relation: annual_checkup
        value: required
    message: "Elderly diabetics need checkups."
""")
        return kb

    def test_all_conditions_met_with_requirement_passes(self):
        kb = self._kb_elderly_diabetic()
        r = kb.verify(response_claims=[
            Claim(subject="patient", relation="age", object="70"),
            Claim(subject="patient", relation="condition", object="diabetes"),
            Claim(subject="patient", relation="annual_checkup", object="required"),
        ])
        assert not r.is_hallucinating

    def test_all_conditions_met_without_requirement_fails(self):
        kb = self._kb_elderly_diabetic()
        r = kb.verify(response_claims=[
            Claim(subject="patient", relation="age", object="70"),
            Claim(subject="patient", relation="condition", object="diabetes"),
            Claim(subject="patient", relation="annual_checkup", object="not_done"),
        ])
        assert r.is_hallucinating

    def test_condition_not_met_skips_rule(self):
        """Young patient → rule doesn't apply."""
        kb = self._kb_elderly_diabetic()
        r = kb.verify(response_claims=[
            Claim(subject="patient", relation="age", object="40"),
            Claim(subject="patient", relation="condition", object="diabetes"),
            Claim(subject="patient", relation="annual_checkup", object="not_done"),
        ])
        assert not r.is_hallucinating

    def test_any_of_first_condition_triggers(self):
        kb = KnowledgeBase()
        kb.load_string("""
axiomguard: "0.7"
domain: test
rules:
  - name: high_risk
    type: composition
    any_of:
      - entity: patient
        relation: condition
        value: heart_disease
      - entity: patient
        relation: condition
        value: diabetes
    then:
      require:
        relation: risk_level
        value: high
    message: "High risk patient."
""")
        r = kb.verify(response_claims=[
            Claim(subject="patient", relation="condition", object="heart_disease"),
            Claim(subject="patient", relation="risk_level", object="high"),
        ])
        assert not r.is_hallucinating

    def test_any_of_no_condition_met_skips(self):
        kb = KnowledgeBase()
        kb.load_string("""
axiomguard: "0.7"
domain: test
rules:
  - name: high_risk
    type: composition
    any_of:
      - entity: patient
        relation: condition
        value: heart_disease
      - entity: patient
        relation: condition
        value: diabetes
    then:
      require:
        relation: risk_level
        value: high
    message: "High risk patient."
""")
        r = kb.verify(response_claims=[
            Claim(subject="patient", relation="condition", object="flu"),
            Claim(subject="patient", relation="risk_level", object="low"),
        ])
        assert not r.is_hallucinating

    def test_none_of_forbids_conditions(self):
        kb = KnowledgeBase()
        kb.load_string("""
axiomguard: "0.7"
domain: test
rules:
  - name: no_banned_substances
    type: composition
    none_of:
      - entity: employee
        relation: test_result
        value: positive
    then:
      require:
        relation: clearance
        value: granted
    message: "Clearance denied if test positive."
""")
        # positive test → clearance should be denied, not granted
        # But none_of means: NOT(positive) → require clearance=granted
        # If test IS positive, none_of is false, rule doesn't apply
        r = kb.verify(response_claims=[
            Claim(subject="employee", relation="test_result", object="positive"),
            Claim(subject="employee", relation="clearance", object="denied"),
        ])
        assert not r.is_hallucinating

    def test_violated_rules_has_message(self):
        kb = self._kb_elderly_diabetic()
        r = kb.verify(response_claims=[
            Claim(subject="patient", relation="age", object="70"),
            Claim(subject="patient", relation="condition", object="diabetes"),
            Claim(subject="patient", relation="annual_checkup", object="skipped"),
        ])
        assert r.is_hallucinating
        assert any("checkup" in v["message"].lower() for v in r.violated_rules)


# =====================================================================
# Integration: axiom_relations includes new types
# =====================================================================


class TestAxiomRelations:

    def test_comparison_relations_included(self):
        kb = KnowledgeBase()
        kb.load_string("""
axiomguard: "0.7"
domain: test
rules:
  - name: ratio
    type: comparison
    entity: x
    left:
      relation: amount
      value_type: int
    operator: "<="
    right:
      relation: limit
      value_type: int
    message: "Over limit."
""")
        rels = kb.axiom_relations()
        assert "amount" in rels
        assert "limit" in rels

    def test_cardinality_relations_included(self):
        kb = KnowledgeBase()
        kb.load_string("""
axiomguard: "0.7"
domain: test
rules:
  - name: max2
    type: cardinality
    entity: x
    relation: tag
    at_most: 2
    message: "Max 2."
""")
        assert "tag" in kb.axiom_relations()

    def test_composition_relations_included(self):
        kb = KnowledgeBase()
        kb.load_string("""
axiomguard: "0.7"
domain: test
rules:
  - name: comp
    type: composition
    all_of:
      - entity: x
        relation: cond_a
        value: "1"
    then:
      require:
        relation: result
        value: ok
    message: "Test."
""")
        rels = kb.axiom_relations()
        assert "cond_a" in rels
        assert "result" in rels
