"""Tests for temporal reasoning — time-bound constraints with Z3.

Z3 handles all time delta calculations mathematically.
No LLM estimates passage of time.
"""

from datetime import datetime, timezone

import pytest

from axiomguard.knowledge_base import KnowledgeBase, _parse_datetime_to_epoch, _resolve_system_time
from axiomguard.models import Claim
from axiomguard.parser import AxiomParser, TemporalRule, parse_delta


# =====================================================================
# Delta Parsing
# =====================================================================


class TestParseDelta:

    def test_seconds(self):
        assert parse_delta("30s") == 30

    def test_minutes(self):
        assert parse_delta("5m") == 300

    def test_hours(self):
        assert parse_delta("4h") == 14400

    def test_days(self):
        assert parse_delta("7d") == 604800

    def test_weeks(self):
        assert parse_delta("2w") == 1209600

    def test_zero(self):
        assert parse_delta("0s") == 0

    def test_large_value(self):
        assert parse_delta("365d") == 365 * 86400

    def test_whitespace_stripped(self):
        assert parse_delta("  4h  ") == 14400

    def test_invalid_format_raises(self):
        with pytest.raises(ValueError, match="Invalid delta format"):
            parse_delta("4hours")

    def test_no_unit_raises(self):
        with pytest.raises(ValueError, match="Invalid delta format"):
            parse_delta("100")

    def test_empty_raises(self):
        with pytest.raises(ValueError, match="Invalid delta format"):
            parse_delta("")


# =====================================================================
# Datetime Parsing
# =====================================================================


class TestDatetimeParsing:

    def test_iso_format(self):
        epoch = _parse_datetime_to_epoch("2026-03-29T10:00:00")
        # Should be a reasonable epoch value
        assert epoch > 1_000_000_000

    def test_iso_with_timezone(self):
        epoch = _parse_datetime_to_epoch("2026-03-29T10:00:00+07:00")
        assert epoch > 1_000_000_000

    def test_epoch_integer_string(self):
        assert _parse_datetime_to_epoch("1711699200") == 1711699200

    def test_system_time_resolve_none_defaults_to_now(self):
        epoch = _resolve_system_time(None)
        now = int(datetime.now(timezone.utc).timestamp())
        assert abs(epoch - now) < 5  # within 5 seconds

    def test_system_time_resolve_int(self):
        assert _resolve_system_time(1711699200) == 1711699200

    def test_system_time_resolve_string(self):
        epoch = _resolve_system_time("2026-03-29T10:00:00")
        assert epoch > 1_000_000_000

    def test_system_time_resolve_datetime(self):
        dt = datetime(2026, 3, 29, 10, 0, 0, tzinfo=timezone.utc)
        epoch = _resolve_system_time(dt)
        assert epoch == int(dt.timestamp())


# =====================================================================
# TemporalRule YAML Parsing
# =====================================================================


class TestTemporalRuleParsing:

    def test_parse_basic_temporal(self):
        parser = AxiomParser()
        ruleset = parser.load_string("""
axiomguard: "0.3"
domain: medical
rules:
  - name: review_overdue
    type: temporal
    entity: patient
    relation: last_review_time
    reference: system_time
    max_delta: "4h"
    severity: error
    message: "Review overdue — must be within 4 hours."
""")
        assert len(ruleset.rules) == 1
        rule = ruleset.rules[0]
        assert isinstance(rule, TemporalRule)
        assert rule.relation == "last_review_time"
        assert rule.reference == "system_time"
        assert rule.max_delta == "4h"
        assert rule.min_delta is None

    def test_parse_event_vs_event(self):
        parser = AxiomParser()
        ruleset = parser.load_string("""
axiomguard: "0.3"
domain: medical
rules:
  - name: min_stay
    type: temporal
    entity: patient
    relation: admission_time
    reference: discharge_time
    min_delta: "1h"
    severity: error
    message: "Must stay at least 1 hour."
""")
        rule = ruleset.rules[0]
        assert isinstance(rule, TemporalRule)
        assert rule.reference == "discharge_time"
        assert rule.min_delta == "1h"

    def test_parse_both_bounds(self):
        parser = AxiomParser()
        ruleset = parser.load_string("""
axiomguard: "0.3"
domain: auth
rules:
  - name: token_validity
    type: temporal
    entity: session
    relation: token_issued_at
    reference: system_time
    min_delta: "0s"
    max_delta: "1h"
    severity: error
    message: "Token must be 0-1 hour old."
""")
        rule = ruleset.rules[0]
        assert rule.min_delta == "0s"
        assert rule.max_delta == "1h"

    def test_no_delta_raises(self):
        parser = AxiomParser()
        with pytest.raises(Exception):  # Pydantic ValidationError
            parser.load_string("""
axiomguard: "0.3"
domain: test
rules:
  - name: bad_rule
    type: temporal
    entity: patient
    relation: some_time
    severity: error
    message: "Missing delta."
""")

    def test_invalid_delta_format_raises(self):
        parser = AxiomParser()
        with pytest.raises(Exception):
            parser.load_string("""
axiomguard: "0.3"
domain: test
rules:
  - name: bad_delta
    type: temporal
    entity: patient
    relation: some_time
    max_delta: "4hours"
    severity: error
    message: "Bad format."
""")

    def test_default_reference_is_system_time(self):
        parser = AxiomParser()
        ruleset = parser.load_string("""
axiomguard: "0.3"
domain: test
rules:
  - name: simple
    type: temporal
    entity: e
    relation: r
    max_delta: "1h"
    severity: error
    message: "test"
""")
        assert ruleset.rules[0].reference == "system_time"


# =====================================================================
# Z3 Temporal Verification — Event vs System Time
# =====================================================================


class TestTemporalVerification:

    REVIEW_RULE_YAML = """
axiomguard: "0.3"
domain: medical
rules:
  - name: review_overdue
    type: temporal
    entity: patient
    relation: last_review_time
    reference: system_time
    max_delta: "4h"
    severity: error
    message: "Medication review overdue — must be within 4 hours."
"""

    def test_within_time_limit_passes(self):
        """Review 2 hours ago, limit 4 hours → SAT."""
        kb = KnowledgeBase()
        kb.load_string(self.REVIEW_RULE_YAML)

        # system_time = 1000000 (arbitrary epoch)
        # last_review = 992800 (2 hours = 7200 seconds ago)
        result = kb.verify(
            response_claims=[
                Claim(subject="patient_1", relation="last_review_time", object="992800"),
            ],
            system_time=1000000,
        )
        assert not result.is_hallucinating

    def test_exceeded_time_limit_fails(self):
        """Review 5 hours ago, limit 4 hours → UNSAT."""
        kb = KnowledgeBase()
        kb.load_string(self.REVIEW_RULE_YAML)

        # system_time = 1000000
        # last_review = 982000 (18000 seconds = 5 hours ago)
        result = kb.verify(
            response_claims=[
                Claim(subject="patient_1", relation="last_review_time", object="982000"),
            ],
            system_time=1000000,
        )
        assert result.is_hallucinating
        assert "review_overdue" in str(result.violated_rules)

    def test_exact_boundary_passes(self):
        """Review exactly 4 hours ago, limit 4 hours → SAT (<=)."""
        kb = KnowledgeBase()
        kb.load_string(self.REVIEW_RULE_YAML)

        # 4h = 14400 seconds
        result = kb.verify(
            response_claims=[
                Claim(subject="patient_1", relation="last_review_time", object="985600"),
            ],
            system_time=1000000,  # 1000000 - 985600 = 14400 = exactly 4h
        )
        assert not result.is_hallucinating

    def test_iso_datetime_claims(self):
        """Claims can use ISO datetime strings."""
        kb = KnowledgeBase()
        kb.load_string(self.REVIEW_RULE_YAML)

        # Parse both to epoch, check the math
        review_time = "2026-03-29T08:00:00+00:00"  # 8 AM UTC
        system_time = "2026-03-29T14:00:00+00:00"  # 2 PM UTC (6 hours later)

        result = kb.verify(
            response_claims=[
                Claim(subject="patient_1", relation="last_review_time", object=review_time),
            ],
            system_time=system_time,
        )
        # 6 hours > 4 hours → UNSAT
        assert result.is_hallucinating

    def test_iso_datetime_within_limit(self):
        """ISO datetime within time limit → SAT."""
        kb = KnowledgeBase()
        kb.load_string(self.REVIEW_RULE_YAML)

        review_time = "2026-03-29T12:00:00+00:00"  # noon
        system_time = "2026-03-29T14:00:00+00:00"  # 2 PM (2 hours later)

        result = kb.verify(
            response_claims=[
                Claim(subject="patient_1", relation="last_review_time", object=review_time),
            ],
            system_time=system_time,
        )
        assert not result.is_hallucinating

    def test_violated_rules_has_message(self):
        """Violation should include the hardcoded YAML message."""
        kb = KnowledgeBase()
        kb.load_string(self.REVIEW_RULE_YAML)

        result = kb.verify(
            response_claims=[
                Claim(subject="patient_1", relation="last_review_time", object="900000"),
            ],
            system_time=1000000,  # 100000s = ~27.7 hours ago
        )
        assert result.is_hallucinating
        assert len(result.violated_rules) >= 1
        assert result.violated_rules[0]["message"] == "Medication review overdue — must be within 4 hours."


# =====================================================================
# Z3 Temporal Verification — Event vs Event
# =====================================================================


class TestTemporalEventVsEvent:

    STAY_RULE_YAML = """
axiomguard: "0.3"
domain: medical
rules:
  - name: min_hospital_stay
    type: temporal
    entity: patient
    relation: admission_time
    reference: discharge_time
    min_delta: "1h"
    severity: error
    message: "Patient must stay at least 1 hour."
"""

    def test_sufficient_stay_passes(self):
        """Admitted at 10:00, discharged at 14:00 (4h stay) → SAT."""
        kb = KnowledgeBase()
        kb.load_string(self.STAY_RULE_YAML)

        # admission = 1000000, discharge = 1014400 (4h later)
        result = kb.verify(
            response_claims=[
                Claim(subject="patient_1", relation="admission_time", object="1000000"),
                Claim(subject="patient_1", relation="discharge_time", object="1014400"),
            ],
        )
        assert not result.is_hallucinating

    def test_insufficient_stay_fails(self):
        """Admitted at 10:00, discharged at 10:30 (30min stay) → UNSAT."""
        kb = KnowledgeBase()
        kb.load_string(self.STAY_RULE_YAML)

        # admission = 1000000, discharge = 1001800 (30min later)
        result = kb.verify(
            response_claims=[
                Claim(subject="patient_1", relation="admission_time", object="1000000"),
                Claim(subject="patient_1", relation="discharge_time", object="1001800"),
            ],
        )
        assert result.is_hallucinating
        assert "min_hospital_stay" in str(result.violated_rules)

    def test_exact_boundary_event_vs_event(self):
        """Exactly 1 hour stay → SAT (>=)."""
        kb = KnowledgeBase()
        kb.load_string(self.STAY_RULE_YAML)

        result = kb.verify(
            response_claims=[
                Claim(subject="patient_1", relation="admission_time", object="1000000"),
                Claim(subject="patient_1", relation="discharge_time", object="1003600"),
            ],
        )
        assert not result.is_hallucinating


# =====================================================================
# Z3 Temporal — Both Bounds (min + max)
# =====================================================================


class TestTemporalBothBounds:

    TOKEN_RULE_YAML = """
axiomguard: "0.3"
domain: auth
rules:
  - name: token_validity
    type: temporal
    entity: session
    relation: token_issued_at
    reference: system_time
    min_delta: "0s"
    max_delta: "1h"
    severity: error
    message: "Token must be valid (0-1 hour old)."
"""

    def test_valid_token_passes(self):
        """Token issued 30 minutes ago → SAT."""
        kb = KnowledgeBase()
        kb.load_string(self.TOKEN_RULE_YAML)

        result = kb.verify(
            response_claims=[
                Claim(subject="session_1", relation="token_issued_at", object="998200"),
            ],
            system_time=1000000,  # 1800s = 30min ago
        )
        assert not result.is_hallucinating

    def test_expired_token_fails(self):
        """Token issued 2 hours ago → UNSAT (exceeds max_delta)."""
        kb = KnowledgeBase()
        kb.load_string(self.TOKEN_RULE_YAML)

        result = kb.verify(
            response_claims=[
                Claim(subject="session_1", relation="token_issued_at", object="992800"),
            ],
            system_time=1000000,  # 7200s = 2 hours ago
        )
        assert result.is_hallucinating

    def test_future_token_fails(self):
        """Token issued in the future → UNSAT (violates min_delta >= 0)."""
        kb = KnowledgeBase()
        kb.load_string(self.TOKEN_RULE_YAML)

        result = kb.verify(
            response_claims=[
                Claim(subject="session_1", relation="token_issued_at", object="1001000"),
            ],
            system_time=1000000,  # token is 1000s in the future
        )
        assert result.is_hallucinating


# =====================================================================
# KnowledgeBase Integration
# =====================================================================


class TestTemporalIntegration:

    def test_axiom_relations_includes_temporal(self):
        kb = KnowledgeBase()
        kb.load_string("""
axiomguard: "0.3"
domain: test
rules:
  - name: timeout
    type: temporal
    entity: e
    relation: last_event
    reference: system_time
    max_delta: "1h"
    severity: error
    message: "Timeout."
""")
        rels = kb.axiom_relations()
        assert "last_event" in rels

    def test_axiom_relations_includes_reference_relation(self):
        kb = KnowledgeBase()
        kb.load_string("""
axiomguard: "0.3"
domain: test
rules:
  - name: stay
    type: temporal
    entity: e
    relation: start_time
    reference: end_time
    min_delta: "1h"
    severity: error
    message: "Min 1h."
""")
        rels = kb.axiom_relations()
        assert "start_time" in rels
        assert "end_time" in rels

    def test_temporal_with_other_rules(self):
        """Temporal rules coexist with other rule types."""
        kb = KnowledgeBase()
        kb.load_string("""
axiomguard: "0.3"
domain: hospital
rules:
  - name: one_blood_type
    type: unique
    entity: patient
    relation: blood_type
    severity: error
    message: "One blood type."
  - name: review_timeout
    type: temporal
    entity: patient
    relation: last_review_time
    max_delta: "4h"
    severity: error
    message: "Review overdue."
""")
        assert kb.rule_count == 2
        assert "blood_type" in kb.axiom_relations()
        assert "last_review_time" in kb.axiom_relations()

        # Unique rule still works
        result = kb.verify(
            response_claims=[
                Claim(subject="p1", relation="blood_type", object="A"),
            ],
            axiom_claims=[
                Claim(subject="p1", relation="blood_type", object="O"),
            ],
            system_time=1000000,
        )
        assert result.is_hallucinating

    def test_no_system_time_defaults_to_now(self):
        """If system_time is not passed, defaults to current time."""
        kb = KnowledgeBase()
        kb.load_string("""
axiomguard: "0.3"
domain: test
rules:
  - name: recent_event
    type: temporal
    entity: e
    relation: event_time
    max_delta: "1h"
    severity: error
    message: "Must be within 1 hour."
""")
        # Event time very far in the past → should fail with default system_time
        result = kb.verify(
            response_claims=[
                Claim(subject="e1", relation="event_time", object="100000"),
            ],
        )
        assert result.is_hallucinating

    def test_system_time_not_injected_without_temporal_rules(self):
        """Non-temporal rules should work fine without system_time."""
        kb = KnowledgeBase()
        kb.load_string("""
axiomguard: "0.3"
domain: test
rules:
  - name: simple_unique
    type: unique
    entity: company
    relation: ceo
    severity: error
    message: "One CEO."
""")
        # Should not inject system_time, should work normally
        result = kb.verify(
            response_claims=[
                Claim(subject="acme", relation="ceo", object="Alice"),
            ],
            axiom_claims=[
                Claim(subject="acme", relation="ceo", object="Bob"),
            ],
        )
        assert result.is_hallucinating


# =====================================================================
# Real-World Scenarios
# =====================================================================


class TestTemporalScenarios:

    def test_medication_cooldown(self):
        """Cannot administer the same medication within 6 hours."""
        kb = KnowledgeBase()
        kb.load_string("""
axiomguard: "0.3"
domain: medical
rules:
  - name: medication_cooldown
    type: temporal
    entity: patient
    relation: last_dose_time
    reference: system_time
    min_delta: "6h"
    severity: error
    message: "Must wait 6 hours between doses."
""")
        # Last dose 2 hours ago — too soon
        result = kb.verify(
            response_claims=[
                Claim(subject="patient_1", relation="last_dose_time", object="992800"),
            ],
            system_time=1000000,  # 7200s = 2h ago
        )
        assert result.is_hallucinating
        assert result.violated_rules[0]["message"] == "Must wait 6 hours between doses."

        # Last dose 8 hours ago — OK
        result2 = kb.verify(
            response_claims=[
                Claim(subject="patient_1", relation="last_dose_time", object="971200"),
            ],
            system_time=1000000,  # 28800s = 8h ago
        )
        assert not result2.is_hallucinating

    def test_loan_processing_deadline(self):
        """Loan application must be processed within 30 days."""
        kb = KnowledgeBase()
        kb.load_string("""
axiomguard: "0.3"
domain: finance
rules:
  - name: processing_deadline
    type: temporal
    entity: application
    relation: submitted_at
    reference: system_time
    max_delta: "30d"
    severity: error
    message: "Application must be processed within 30 days."
""")
        thirty_days = 30 * 86400  # 2592000 seconds
        base = 1000000

        # Submitted 15 days ago → OK
        result = kb.verify(
            response_claims=[
                Claim(subject="app_1", relation="submitted_at",
                      object=str(base - 15 * 86400)),
            ],
            system_time=base,
        )
        assert not result.is_hallucinating

        # Submitted 45 days ago → overdue
        result2 = kb.verify(
            response_claims=[
                Claim(subject="app_1", relation="submitted_at",
                      object=str(base - 45 * 86400)),
            ],
            system_time=base,
        )
        assert result2.is_hallucinating

    def test_access_token_window(self):
        """Access token must be between 0 and 1 hour old."""
        kb = KnowledgeBase()
        kb.load_string("""
axiomguard: "0.3"
domain: auth
rules:
  - name: token_window
    type: temporal
    entity: session
    relation: issued_at
    reference: system_time
    min_delta: "0s"
    max_delta: "1h"
    severity: error
    message: "Token expired or from the future."
""")
        base = 1000000

        # 30 min ago → valid
        assert not kb.verify(
            response_claims=[Claim(subject="s1", relation="issued_at", object=str(base - 1800))],
            system_time=base,
        ).is_hallucinating

        # 2 hours ago → expired
        assert kb.verify(
            response_claims=[Claim(subject="s1", relation="issued_at", object=str(base - 7200))],
            system_time=base,
        ).is_hallucinating

        # In the future → invalid
        assert kb.verify(
            response_claims=[Claim(subject="s1", relation="issued_at", object=str(base + 1000))],
            system_time=base,
        ).is_hallucinating
