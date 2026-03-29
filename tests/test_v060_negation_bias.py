"""Tests for v0.6.0 — NegationRule + Extraction Bias Audit.

Task 1: NegationRule (`must_not_include`) + conditional forbid
Task 2: audit_extraction_bias() — deterministic protected attribute check
"""

import pytest

from axiomguard.core import audit_extraction_bias, DEFAULT_PROTECTED_ATTRIBUTES
from axiomguard.knowledge_base import KnowledgeBase
from axiomguard.models import Claim
from axiomguard.parser import AxiomParser, NegationRule


# =====================================================================
# NegationRule: YAML Parsing
# =====================================================================


class TestNegationParsing:

    def test_single_forbidden_value(self):
        parser = AxiomParser()
        ruleset = parser.load_string("""
axiomguard: "0.3"
domain: medical
rules:
  - name: no_penicillin
    type: negation
    entity: patient
    relation: medication
    must_not_include: Penicillin
    severity: error
    message: "Patient must NOT receive Penicillin."
""")
        rule = ruleset.rules[0]
        assert isinstance(rule, NegationRule)
        assert rule.must_not_include == ["Penicillin"]

    def test_multiple_forbidden_values(self):
        parser = AxiomParser()
        ruleset = parser.load_string("""
axiomguard: "0.3"
domain: hr
rules:
  - name: banned_substances
    type: negation
    entity: employee
    relation: substance_test
    must_not_include:
      - Methamphetamine
      - Cocaine
      - Heroin
    severity: error
    message: "Banned substance detected."
""")
        rule = ruleset.rules[0]
        assert len(rule.must_not_include) == 3
        assert "Cocaine" in rule.must_not_include

    def test_empty_must_not_include_raises(self):
        parser = AxiomParser()
        with pytest.raises(Exception):
            parser.load_string("""
axiomguard: "0.3"
domain: test
rules:
  - name: bad
    type: negation
    entity: e
    relation: r
    must_not_include: []
    severity: error
    message: "Empty."
""")

    def test_string_auto_wrapped_to_list(self):
        """Single string value is automatically wrapped in a list."""
        parser = AxiomParser()
        ruleset = parser.load_string("""
axiomguard: "0.3"
domain: test
rules:
  - name: single
    type: negation
    entity: e
    relation: r
    must_not_include: forbidden_value
    severity: error
    message: "test"
""")
        assert ruleset.rules[0].must_not_include == ["forbidden_value"]


# =====================================================================
# NegationRule: Z3 Verification
# =====================================================================


class TestNegationVerification:

    def test_allowed_value_passes(self):
        """Claim with non-forbidden value → SAT."""
        kb = KnowledgeBase()
        kb.load_string("""
axiomguard: "0.3"
domain: medical
rules:
  - name: no_penicillin
    type: negation
    entity: patient
    relation: medication
    must_not_include: Penicillin
    severity: error
    message: "Must NOT receive Penicillin."
""")
        result = kb.verify(
            response_claims=[
                Claim(subject="patient_1", relation="medication", object="Paracetamol"),
            ],
        )
        assert not result.is_hallucinating

    def test_forbidden_value_fails(self):
        """Claim with forbidden value → UNSAT."""
        kb = KnowledgeBase()
        kb.load_string("""
axiomguard: "0.3"
domain: medical
rules:
  - name: no_penicillin
    type: negation
    entity: patient
    relation: medication
    must_not_include: Penicillin
    severity: error
    message: "Must NOT receive Penicillin."
""")
        result = kb.verify(
            response_claims=[
                Claim(subject="patient_1", relation="medication", object="Penicillin"),
            ],
        )
        assert result.is_hallucinating
        assert "no_penicillin" in str(result.violated_rules)

    def test_multiple_forbidden_one_hit(self):
        """One of multiple forbidden values present → UNSAT."""
        kb = KnowledgeBase()
        kb.load_string("""
axiomguard: "0.3"
domain: hr
rules:
  - name: banned
    type: negation
    entity: employee
    relation: substance_test
    must_not_include: [Methamphetamine, Cocaine, Heroin]
    severity: error
    message: "Banned substance."
""")
        result = kb.verify(
            response_claims=[
                Claim(subject="emp_1", relation="substance_test", object="Cocaine"),
            ],
        )
        assert result.is_hallucinating

    def test_multiple_forbidden_none_hit(self):
        """None of the forbidden values present → SAT."""
        kb = KnowledgeBase()
        kb.load_string("""
axiomguard: "0.3"
domain: hr
rules:
  - name: banned
    type: negation
    entity: employee
    relation: substance_test
    must_not_include: [Methamphetamine, Cocaine, Heroin]
    severity: error
    message: "Banned substance."
""")
        result = kb.verify(
            response_claims=[
                Claim(subject="emp_1", relation="substance_test", object="Negative"),
            ],
        )
        assert not result.is_hallucinating

    def test_violated_rules_has_message(self):
        """Violation includes hardcoded YAML message."""
        kb = KnowledgeBase()
        kb.load_string("""
axiomguard: "0.3"
domain: medical
rules:
  - name: no_aspirin
    type: negation
    entity: patient
    relation: medication
    must_not_include: Aspirin
    severity: error
    message: "Aspirin is contraindicated."
""")
        result = kb.verify(
            response_claims=[
                Claim(subject="p1", relation="medication", object="Aspirin"),
            ],
        )
        assert result.violated_rules[0]["message"] == "Aspirin is contraindicated."

    def test_negation_with_other_rules(self):
        """Negation coexists with unique + exclusion rules."""
        kb = KnowledgeBase()
        kb.load_string("""
axiomguard: "0.3"
domain: medical
rules:
  - name: one_blood_type
    type: unique
    entity: patient
    relation: blood_type
    severity: error
    message: "One blood type."
  - name: no_penicillin
    type: negation
    entity: patient
    relation: medication
    must_not_include: Penicillin
    severity: error
    message: "No Penicillin."
""")
        # Penicillin → UNSAT
        result = kb.verify(
            response_claims=[
                Claim(subject="p1", relation="medication", object="Penicillin"),
            ],
        )
        assert result.is_hallucinating

        # Paracetamol → SAT
        result2 = kb.verify(
            response_claims=[
                Claim(subject="p1", relation="medication", object="Paracetamol"),
            ],
        )
        assert not result2.is_hallucinating

    def test_axiom_relations_includes_negation(self):
        kb = KnowledgeBase()
        kb.load_string("""
axiomguard: "0.3"
domain: test
rules:
  - name: no_x
    type: negation
    entity: e
    relation: forbidden_rel
    must_not_include: x
    severity: error
    message: "test"
""")
        assert "forbidden_rel" in kb.axiom_relations()


# =====================================================================
# Conditional Forbid (dependency + then.forbid)
# =====================================================================


class TestConditionalForbid:

    def test_condition_met_forbidden_value_fails(self):
        """Allergy=Penicillin + med=Amoxicillin → UNSAT."""
        kb = KnowledgeBase()
        kb.load_string("""
axiomguard: "0.3"
domain: medical
rules:
  - name: allergy_cross_reactivity
    type: dependency
    when:
      entity: patient
      relation: allergy
      value: Penicillin
    then:
      forbid:
        relation: medication
        values: [Amoxicillin, Ampicillin, Cephalexin]
    severity: error
    message: "Cross-reactive antibiotics forbidden for Penicillin-allergic patients."
""")
        result = kb.verify(
            response_claims=[
                Claim(subject="patient_1", relation="medication", object="Amoxicillin"),
            ],
            axiom_claims=[
                Claim(subject="patient_1", relation="allergy", object="Penicillin"),
            ],
        )
        assert result.is_hallucinating

    def test_condition_met_safe_value_passes(self):
        """Allergy=Penicillin + med=Metformin (not in forbid list) → SAT."""
        kb = KnowledgeBase()
        kb.load_string("""
axiomguard: "0.3"
domain: medical
rules:
  - name: allergy_cross_reactivity
    type: dependency
    when:
      entity: patient
      relation: allergy
      value: Penicillin
    then:
      forbid:
        relation: medication
        values: [Amoxicillin, Ampicillin]
    severity: error
    message: "Cross-reactive forbidden."
""")
        result = kb.verify(
            response_claims=[
                Claim(subject="patient_1", relation="medication", object="Metformin"),
            ],
            axiom_claims=[
                Claim(subject="patient_1", relation="allergy", object="Penicillin"),
            ],
        )
        assert not result.is_hallucinating

    def test_condition_not_met_forbidden_value_passes(self):
        """Allergy=Shellfish + med=Amoxicillin (condition not met) → SAT."""
        kb = KnowledgeBase()
        kb.load_string("""
axiomguard: "0.3"
domain: medical
rules:
  - name: allergy_cross_reactivity
    type: dependency
    when:
      entity: patient
      relation: allergy
      value: Penicillin
    then:
      forbid:
        relation: medication
        values: [Amoxicillin, Ampicillin]
    severity: error
    message: "Cross-reactive forbidden."
""")
        result = kb.verify(
            response_claims=[
                Claim(subject="patient_1", relation="medication", object="Amoxicillin"),
            ],
            axiom_claims=[
                Claim(subject="patient_1", relation="allergy", object="Shellfish"),
            ],
        )
        assert not result.is_hallucinating


# =====================================================================
# Extraction Bias Audit
# =====================================================================


class TestBiasAudit:

    def test_no_bias_detected(self):
        """Clean claims produce no warnings."""
        claims = [
            Claim(subject="patient_1", relation="medication", object="Aspirin"),
            Claim(subject="company", relation="location", object="Bangkok"),
        ]
        warnings = audit_extraction_bias(claims)
        assert warnings == []

    def test_gender_detected_in_subject(self):
        """'female' in subject triggers warning."""
        claims = [
            Claim(subject="female applicant", relation="recommended_for", object="secretary"),
        ]
        warnings = audit_extraction_bias(claims)
        assert len(warnings) == 1
        assert "female" in warnings[0]

    def test_race_detected_in_object(self):
        """'black' in object triggers warning."""
        claims = [
            Claim(subject="candidate", relation="description", object="black male"),
        ]
        warnings = audit_extraction_bias(claims)
        assert len(warnings) == 1
        assert "black" in warnings[0] or "male" in warnings[0]

    def test_religion_detected(self):
        claims = [
            Claim(subject="muslim employee", relation="department", object="security"),
        ]
        warnings = audit_extraction_bias(claims)
        assert len(warnings) == 1
        assert "muslim" in warnings[0]

    def test_multiple_claims_multiple_flags(self):
        """Each claim flagged independently."""
        claims = [
            Claim(subject="female nurse", relation="role", object="assistant"),
            Claim(subject="young intern", relation="skill", object="limited"),
        ]
        warnings = audit_extraction_bias(claims)
        assert len(warnings) == 2

    def test_one_warning_per_claim(self):
        """Even if claim contains multiple protected terms, only one warning."""
        claims = [
            Claim(subject="elderly disabled woman", relation="status", object="rejected"),
        ]
        warnings = audit_extraction_bias(claims)
        assert len(warnings) == 1  # Not 3

    def test_custom_protected_attributes(self):
        """Custom attributes override defaults."""
        claims = [
            Claim(subject="vegan employee", relation="diet", object="plant-based"),
        ]
        # Default attributes don't include "vegan"
        assert audit_extraction_bias(claims) == []

        # Custom attributes do
        custom = frozenset({"vegan", "vegetarian"})
        warnings = audit_extraction_bias(claims, protected_attributes=custom)
        assert len(warnings) == 1
        assert "vegan" in warnings[0]

    def test_case_insensitive(self):
        """Detection is case-insensitive."""
        claims = [
            Claim(subject="FEMALE Doctor", relation="specialty", object="surgery"),
        ]
        warnings = audit_extraction_bias(claims)
        assert len(warnings) == 1

    def test_relation_also_checked(self):
        """Protected terms in relation are also caught."""
        claims = [
            Claim(subject="applicant", relation="gender", object="male"),
        ]
        warnings = audit_extraction_bias(claims)
        assert len(warnings) == 1

    def test_empty_claims(self):
        """Empty list produces no warnings."""
        assert audit_extraction_bias([]) == []
