"""Tests for v0.6.0 — Confidence Scoring + Enhanced Normalization + Claim Classification.

Task 3: Claim.confidence, hedge word detection, low-confidence routing
Task 4: Enhanced normalization (strip titles/suffixes), RelationDef categories
"""

import pytest

from axiomguard.core import (
    filter_low_confidence,
    score_claim_confidence,
    HEDGE_WORDS,
)
from axiomguard.knowledge_base import KnowledgeBase
from axiomguard.models import Claim
from axiomguard.parser import AxiomParser, RelationDef
from axiomguard.resolver import EntityResolver, normalize_enhanced


# =====================================================================
# Claim.confidence Field
# =====================================================================


class TestClaimConfidence:

    def test_default_confidence_is_1(self):
        claim = Claim(subject="x", relation="y", object="z")
        assert claim.confidence == 1.0

    def test_custom_confidence(self):
        claim = Claim(subject="x", relation="y", object="z", confidence=0.7)
        assert claim.confidence == 0.7

    def test_confidence_bounds(self):
        """Confidence must be 0.0-1.0."""
        with pytest.raises(Exception):
            Claim(subject="x", relation="y", object="z", confidence=1.5)
        with pytest.raises(Exception):
            Claim(subject="x", relation="y", object="z", confidence=-0.1)

    def test_confidence_zero_valid(self):
        claim = Claim(subject="x", relation="y", object="z", confidence=0.0)
        assert claim.confidence == 0.0

    def test_backward_compat_no_confidence(self):
        """Existing code that doesn't pass confidence still works."""
        claim = Claim(subject="company", relation="location", object="Bangkok")
        assert claim.confidence == 1.0


# =====================================================================
# Hedge Word Detection
# =====================================================================


class TestHedgeDetection:

    def test_no_hedge_keeps_confidence(self):
        claim = Claim(subject="company", relation="location", object="Bangkok")
        scored = score_claim_confidence(claim)
        assert scored.confidence == 1.0

    def test_maybe_lowers_confidence(self):
        claim = Claim(subject="company", relation="location", object="maybe Bangkok")
        scored = score_claim_confidence(claim)
        assert scored.confidence == 0.3

    def test_probably_lowers_confidence(self):
        claim = Claim(subject="company", relation="location", object="probably Chiang Mai")
        scored = score_claim_confidence(claim)
        assert scored.confidence == 0.3

    def test_approximately_in_subject(self):
        claim = Claim(subject="approximately 100 employees", relation="count", object="100")
        scored = score_claim_confidence(claim)
        assert scored.confidence == 0.3

    def test_appears_lowers_confidence(self):
        claim = Claim(subject="patient", relation="condition", object="appears healthy")
        scored = score_claim_confidence(claim)
        assert scored.confidence == 0.3

    def test_case_insensitive(self):
        claim = Claim(subject="company", relation="location", object="POSSIBLY Bangkok")
        scored = score_claim_confidence(claim)
        assert scored.confidence == 0.3

    def test_preserves_existing_low_confidence(self):
        """If confidence already set, hedge detection can only lower it."""
        claim = Claim(subject="company", relation="location", object="Bangkok", confidence=0.5)
        scored = score_claim_confidence(claim)
        assert scored.confidence == 0.5  # No hedge → keeps existing


# =====================================================================
# Low-Confidence Routing
# =====================================================================


class TestFilterLowConfidence:

    def test_all_high_confidence(self):
        claims = [
            Claim(subject="a", relation="r", object="1", confidence=1.0),
            Claim(subject="b", relation="r", object="2", confidence=0.8),
        ]
        high, low = filter_low_confidence(claims)
        assert len(high) == 2
        assert len(low) == 0

    def test_all_low_confidence(self):
        claims = [
            Claim(subject="a", relation="r", object="1", confidence=0.3),
            Claim(subject="b", relation="r", object="2", confidence=0.1),
        ]
        high, low = filter_low_confidence(claims)
        assert len(high) == 0
        assert len(low) == 2

    def test_mixed_confidence(self):
        claims = [
            Claim(subject="a", relation="r", object="1", confidence=1.0),
            Claim(subject="b", relation="r", object="maybe 2", confidence=0.3),
            Claim(subject="c", relation="r", object="3", confidence=0.7),
        ]
        high, low = filter_low_confidence(claims)
        assert len(high) == 2  # a (1.0) + c (0.7)
        assert len(low) == 1   # b (0.3)

    def test_custom_threshold(self):
        claims = [
            Claim(subject="a", relation="r", object="1", confidence=0.8),
            Claim(subject="b", relation="r", object="2", confidence=0.6),
        ]
        high, low = filter_low_confidence(claims, threshold=0.7)
        assert len(high) == 1  # a (0.8)
        assert len(low) == 1   # b (0.6)

    def test_exact_threshold_is_high(self):
        claims = [
            Claim(subject="a", relation="r", object="1", confidence=0.5),
        ]
        high, low = filter_low_confidence(claims, threshold=0.5)
        assert len(high) == 1
        assert len(low) == 0

    def test_empty_list(self):
        high, low = filter_low_confidence([])
        assert high == []
        assert low == []


# =====================================================================
# Enhanced Normalization
# =====================================================================


class TestEnhancedNormalization:

    def test_strip_dr(self):
        assert normalize_enhanced("Dr. Smith") == "smith"

    def test_strip_mr(self):
        assert normalize_enhanced("Mr. Johnson") == "johnson"

    def test_strip_prof(self):
        assert normalize_enhanced("Prof. Somchai") == "somchai"

    def test_strip_the(self):
        assert normalize_enhanced("The Company") == "company"

    def test_strip_a(self):
        assert normalize_enhanced("A Patient") == "patient"

    def test_strip_jr(self):
        assert normalize_enhanced("John Jr.") == "john"

    def test_strip_phd(self):
        assert normalize_enhanced("Jane PhD") == "jane"

    def test_strip_inc(self):
        assert normalize_enhanced("Acme Inc.") == "acme"

    def test_strip_multiple(self):
        """Strip title + suffix together."""
        assert normalize_enhanced("Dr. Smith Jr.") == "smith"

    def test_strip_article_and_title(self):
        assert normalize_enhanced("The Dr. House") == "house"

    def test_no_stripping_needed(self):
        assert normalize_enhanced("Bangkok") == "bangkok"

    def test_unicode_normalization(self):
        assert normalize_enhanced("  Café  ") == "café"

    def test_empty_after_strip(self):
        """If everything is stripped, return original normalized."""
        result = normalize_enhanced("The Dr.")
        assert result  # Should not be empty


# =====================================================================
# Relation Classification (YAML)
# =====================================================================


class TestRelationClassification:

    def test_parse_relations(self):
        parser = AxiomParser()
        ruleset = parser.load_string("""
axiomguard: "0.3"
domain: medical
relations:
  - name: blood_type
    category: definitional
    description: "Does not change with context"
  - name: workplace_attire
    category: contingent
  - name: gender_attire
    category: normative_risk
    description: "Statistically true but normatively unacceptable to use"
rules:
  - name: one_blood
    type: unique
    entity: patient
    relation: blood_type
    severity: error
    message: "One blood type."
""")
        assert len(ruleset.relations) == 3
        assert ruleset.relations[0].name == "blood_type"
        assert ruleset.relations[0].category == "definitional"
        assert ruleset.relations[2].category == "normative_risk"

    def test_default_category_is_contingent(self):
        parser = AxiomParser()
        ruleset = parser.load_string("""
axiomguard: "0.3"
domain: test
relations:
  - name: some_relation
rules:
  - name: r
    type: unique
    entity: e
    relation: r
    severity: error
    message: "test"
""")
        assert ruleset.relations[0].category == "contingent"

    def test_no_relations_field_ok(self):
        """Backward compat — relations field is optional."""
        parser = AxiomParser()
        ruleset = parser.load_string("""
axiomguard: "0.3"
domain: test
rules:
  - name: r
    type: unique
    entity: e
    relation: r
    severity: error
    message: "test"
""")
        assert ruleset.relations == []

    def test_kb_stores_categories(self):
        kb = KnowledgeBase()
        kb.load_string("""
axiomguard: "0.3"
domain: medical
relations:
  - name: blood_type
    category: definitional
  - name: attire
    category: normative_risk
rules:
  - name: one_blood
    type: unique
    entity: patient
    relation: blood_type
    severity: error
    message: "One blood type."
""")
        assert kb.relation_category("blood_type") == "definitional"
        assert kb.relation_category("attire") == "normative_risk"
        assert kb.relation_category("unknown") == "contingent"  # default
