"""
Tests for v0.7.x — Conditional Chains (DependencyRule extension).

Tests transitive dependencies: A → B → C.
"""

import pytest

from axiomguard import KnowledgeBase, Claim
from axiomguard.parser import AxiomParser, DependencyRule


# =====================================================================
# Parsing
# =====================================================================


class TestChainParsing:

    def test_parse_single_chain_step(self):
        parser = AxiomParser()
        rs = parser.load_string("""
axiomguard: "0.7"
domain: test
rules:
  - name: approval_chain
    type: dependency
    when:
      entity: applicant
      relation: credit_score
      operator: "<"
      value: "600"
      value_type: int
    then:
      require:
        relation: approval_status
        value: manual_review
    chain:
      - when:
          relation: approval_status
          value: manual_review
        then:
          require:
            relation: reviewer_assigned
            value: required
    message: "Low credit requires manual review."
""")
        rule = rs.rules[0]
        assert isinstance(rule, DependencyRule)
        assert rule.chain is not None
        assert len(rule.chain) == 1
        assert rule.chain[0].when.relation == "approval_status"
        assert rule.chain[0].then.require.value == "required"

    def test_parse_multi_step_chain(self):
        parser = AxiomParser()
        rs = parser.load_string("""
axiomguard: "0.7"
domain: test
rules:
  - name: three_step
    type: dependency
    when:
      entity: order
      relation: amount
      operator: ">"
      value: "10000"
      value_type: int
    then:
      require:
        relation: approval_level
        value: manager
    chain:
      - when:
          relation: approval_level
          value: manager
        then:
          require:
            relation: risk_assessment
            value: completed
      - when:
          relation: risk_assessment
          value: completed
        then:
          require:
            relation: audit_trail
            value: logged
    message: "High-value orders require full chain."
""")
        rule = rs.rules[0]
        assert len(rule.chain) == 2
        assert rule.chain[0].then.require.relation == "risk_assessment"
        assert rule.chain[1].then.require.relation == "audit_trail"

    def test_no_chain_still_works(self):
        parser = AxiomParser()
        rs = parser.load_string("""
axiomguard: "0.7"
domain: test
rules:
  - name: simple
    type: dependency
    when:
      entity: x
      relation: a
      value: "1"
    then:
      require:
        relation: b
        value: "2"
    message: "Simple dep."
""")
        rule = rs.rules[0]
        assert rule.chain is None

    def test_chain_with_forbid(self):
        parser = AxiomParser()
        rs = parser.load_string("""
axiomguard: "0.7"
domain: test
rules:
  - name: forbid_chain
    type: dependency
    when:
      entity: patient
      relation: allergy
      value: penicillin
    then:
      require:
        relation: allergy_flag
        value: active
    chain:
      - when:
          relation: allergy_flag
          value: active
        then:
          forbid:
            relation: medication
            values: [Penicillin, Amoxicillin]
    message: "Allergic patients cannot receive penicillin-class drugs."
""")
        rule = rs.rules[0]
        assert rule.chain[0].then.forbid is not None
        assert "Penicillin" in rule.chain[0].then.forbid.values


# =====================================================================
# Verification
# =====================================================================


class TestChainVerification:

    def _kb_loan_chain(self) -> KnowledgeBase:
        kb = KnowledgeBase()
        kb.load_string("""
axiomguard: "0.7"
domain: test
rules:
  - name: loan_approval_chain
    type: dependency
    when:
      entity: applicant
      relation: credit_score
      operator: "<"
      value: "600"
      value_type: int
    then:
      require:
        relation: approval_status
        value: manual_review
    chain:
      - when:
          relation: approval_status
          value: manual_review
        then:
          require:
            relation: reviewer_assigned
            value: required
    message: "Low credit requires manual review with assigned reviewer."
""")
        return kb

    def test_full_chain_satisfied(self):
        kb = self._kb_loan_chain()
        r = kb.verify(response_claims=[
            Claim(subject="applicant", relation="credit_score", object="500"),
            Claim(subject="applicant", relation="approval_status", object="manual_review"),
            Claim(subject="applicant", relation="reviewer_assigned", object="required"),
        ])
        assert not r.is_hallucinating

    def test_chain_step_violated(self):
        """manual_review triggered but reviewer not assigned."""
        kb = self._kb_loan_chain()
        r = kb.verify(response_claims=[
            Claim(subject="applicant", relation="credit_score", object="500"),
            Claim(subject="applicant", relation="approval_status", object="manual_review"),
            Claim(subject="applicant", relation="reviewer_assigned", object="not_assigned"),
        ])
        assert r.is_hallucinating

    def test_first_step_violated(self):
        """Low credit but approval_status is not manual_review."""
        kb = self._kb_loan_chain()
        r = kb.verify(response_claims=[
            Claim(subject="applicant", relation="credit_score", object="500"),
            Claim(subject="applicant", relation="approval_status", object="auto_approved"),
        ])
        assert r.is_hallucinating

    def test_condition_not_met_skips_chain(self):
        """High credit → entire chain doesn't apply."""
        kb = self._kb_loan_chain()
        r = kb.verify(response_claims=[
            Claim(subject="applicant", relation="credit_score", object="800"),
            Claim(subject="applicant", relation="approval_status", object="auto_approved"),
        ])
        assert not r.is_hallucinating

    def test_three_step_chain(self):
        kb = KnowledgeBase()
        kb.load_string("""
axiomguard: "0.7"
domain: test
rules:
  - name: three_step
    type: dependency
    when:
      entity: order
      relation: priority
      value: urgent
    then:
      require:
        relation: approval
        value: manager
    chain:
      - when:
          relation: approval
          value: manager
        then:
          require:
            relation: risk_check
            value: done
      - when:
          relation: risk_check
          value: done
        then:
          require:
            relation: audit
            value: logged
    message: "Urgent orders need full chain."
""")
        # Full chain satisfied
        r = kb.verify(response_claims=[
            Claim(subject="order", relation="priority", object="urgent"),
            Claim(subject="order", relation="approval", object="manager"),
            Claim(subject="order", relation="risk_check", object="done"),
            Claim(subject="order", relation="audit", object="logged"),
        ])
        assert not r.is_hallucinating

        # Last step missing
        r2 = kb.verify(response_claims=[
            Claim(subject="order", relation="priority", object="urgent"),
            Claim(subject="order", relation="approval", object="manager"),
            Claim(subject="order", relation="risk_check", object="done"),
            Claim(subject="order", relation="audit", object="not_logged"),
        ])
        assert r2.is_hallucinating

    def test_chain_with_forbid(self):
        kb = KnowledgeBase()
        kb.load_string("""
axiomguard: "0.7"
domain: test
rules:
  - name: allergy_chain
    type: dependency
    when:
      entity: patient
      relation: allergy
      value: penicillin
    then:
      require:
        relation: allergy_flag
        value: active
    chain:
      - when:
          relation: allergy_flag
          value: active
        then:
          forbid:
            relation: medication
            values: [Penicillin, Amoxicillin]
    message: "Allergic patients cannot receive penicillin-class drugs."
""")
        # Allergic + flag active + no banned meds → OK
        r = kb.verify(response_claims=[
            Claim(subject="patient", relation="allergy", object="penicillin"),
            Claim(subject="patient", relation="allergy_flag", object="active"),
            Claim(subject="patient", relation="medication", object="Ibuprofen"),
        ])
        assert not r.is_hallucinating

        # Allergic + flag active + banned med → FAIL
        r2 = kb.verify(response_claims=[
            Claim(subject="patient", relation="allergy", object="penicillin"),
            Claim(subject="patient", relation="allergy_flag", object="active"),
            Claim(subject="patient", relation="medication", object="Penicillin"),
        ])
        assert r2.is_hallucinating


# =====================================================================
# axiom_relations includes chain relations
# =====================================================================


class TestChainRelations:

    def test_chain_relations_included(self):
        kb = KnowledgeBase()
        kb.load_string("""
axiomguard: "0.7"
domain: test
rules:
  - name: chain_test
    type: dependency
    when:
      entity: x
      relation: a
      value: "1"
    then:
      require:
        relation: b
        value: "2"
    chain:
      - when:
          relation: b
          value: "2"
        then:
          require:
            relation: c
            value: "3"
    message: "Chain."
""")
        rels = kb.axiom_relations()
        assert "a" in rels
        assert "b" in rels
        assert "c" in rels
