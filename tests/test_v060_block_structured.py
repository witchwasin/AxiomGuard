"""Tests for v0.6.0 — Block-and-Escalate mode + Structured Input Path.

Phase 2: mode="correct" | "block" | "escalate" in generate_with_guard()
Phase 3: verify_structured() — JSON/Claim input, no LLM extraction
"""

import pytest

from axiomguard.core import generate_with_guard, verify_structured
from axiomguard.knowledge_base import KnowledgeBase
from axiomguard.models import Claim, CorrectionResult


# =====================================================================
# Shared fixtures
# =====================================================================

_MEDICAL_RULES = """
axiomguard: "0.3"
domain: medical
entities:
  - name: patient
    aliases: ["pt"]
rules:
  - name: drug_interaction
    type: exclusion
    entity: patient
    relation: takes
    values: [Warfarin, Aspirin]
    severity: error
    message: "CRITICAL: Warfarin + Aspirin = bleeding risk."
  - name: one_blood_type
    type: unique
    entity: patient
    relation: blood_type
    severity: error
    message: "Patient cannot have two blood types."
  - name: one_location
    type: unique
    entity: company
    relation: location
    severity: error
    message: "Company can only have one location."
"""


def _make_kb() -> KnowledgeBase:
    kb = KnowledgeBase()
    kb.load_string(_MEDICAL_RULES)
    return kb


# =====================================================================
# Phase 2: Block-and-Escalate Mode
# =====================================================================


class TestBlockMode:
    """mode='block' — halt immediately on UNSAT, no retries."""

    def test_block_returns_blocked_on_violation(self):
        """If Z3 returns UNSAT, status is 'blocked' with no retries."""
        kb = _make_kb()

        # Mock LLM returns something the mock extractor parses as location "Chiang Mai"
        def bad_llm(prompt):
            return "The company is in Chiang Mai."

        # Axiom says company is in Bangkok → unique relation conflict
        result = generate_with_guard(
            prompt="Where is the company?",
            kb=kb,
            llm_generate=bad_llm,
            axiom_claims=[Claim(subject="company", relation="location", object="Bangkok")],
            mode="block",
        )

        assert result.status == "blocked"
        assert result.attempts == 1
        assert result.max_attempts == 1
        assert result.final_verification is not None
        assert result.final_verification.is_hallucinating

    def test_block_returns_verified_on_pass(self):
        """If Z3 returns SAT, behaves identically to correct mode."""
        kb = _make_kb()

        def good_llm(prompt):
            return "The company is in Bangkok."

        result = generate_with_guard(
            prompt="Where is the company?",
            kb=kb,
            llm_generate=good_llm,
            axiom_claims=[Claim(subject="company", relation="location", object="Bangkok")],
            mode="block",
        )

        assert result.status == "verified"
        assert result.attempts == 1

    def test_block_no_retries_even_with_max_retries_set(self):
        """max_retries is ignored in block mode."""
        kb = _make_kb()

        call_count = 0
        def counting_llm(prompt):
            nonlocal call_count
            call_count += 1
            return "The company is in Chiang Mai."

        result = generate_with_guard(
            prompt="Where?",
            kb=kb,
            llm_generate=counting_llm,
            axiom_claims=[Claim(subject="company", relation="location", object="Bangkok")],
            max_retries=5,  # Should be ignored
            mode="block",
        )

        assert result.status == "blocked"
        assert call_count == 1  # Only called once
        assert result.attempts == 1

    def test_block_has_violated_rules(self):
        """Blocked result should include verification details."""
        kb = _make_kb()

        def bad_llm(prompt):
            return "The company is in Chiang Mai."

        result = generate_with_guard(
            prompt="test",
            kb=kb,
            llm_generate=bad_llm,
            axiom_claims=[Claim(subject="company", relation="location", object="Bangkok")],
            mode="block",
        )

        assert result.status == "blocked"
        assert result.final_verification is not None
        assert result.final_verification.is_hallucinating


class TestEscalateMode:
    """mode='escalate' — block + call on_escalate callback."""

    def test_escalate_calls_callback(self):
        """on_escalate callback is invoked with the blocked result."""
        kb = _make_kb()
        escalated_results = []

        def on_escalate(result):
            escalated_results.append(result)

        def bad_llm(prompt):
            return "The company is in Chiang Mai."

        result = generate_with_guard(
            prompt="test",
            kb=kb,
            llm_generate=bad_llm,
            axiom_claims=[Claim(subject="company", relation="location", object="Bangkok")],
            mode="escalate",
            on_escalate=on_escalate,
        )

        assert result.status == "blocked"
        assert len(escalated_results) == 1
        assert escalated_results[0].status == "blocked"
        assert escalated_results[0] is result

    def test_escalate_not_called_on_pass(self):
        """on_escalate is NOT called when verification passes."""
        kb = _make_kb()
        escalated_results = []

        def on_escalate(result):
            escalated_results.append(result)

        def good_llm(prompt):
            return "The company is in Bangkok."

        result = generate_with_guard(
            prompt="test",
            kb=kb,
            llm_generate=good_llm,
            axiom_claims=[Claim(subject="company", relation="location", object="Bangkok")],
            mode="escalate",
            on_escalate=on_escalate,
        )

        assert result.status == "verified"
        assert len(escalated_results) == 0  # Not called

    def test_escalate_requires_callback(self):
        """mode='escalate' without on_escalate raises ValueError."""
        kb = _make_kb()

        with pytest.raises(ValueError, match="on_escalate"):
            generate_with_guard(
                prompt="test",
                kb=kb,
                llm_generate=lambda p: "test",
                mode="escalate",
                # on_escalate not provided
            )

    def test_invalid_mode_raises(self):
        """Unknown mode raises ValueError."""
        kb = _make_kb()

        with pytest.raises(ValueError, match="Invalid mode"):
            generate_with_guard(
                prompt="test",
                kb=kb,
                llm_generate=lambda p: "test",
                mode="invalid_mode",
            )


class TestCorrectModeBackwardCompat:
    """mode='correct' (default) — existing retry behavior unchanged."""

    def test_default_mode_is_correct(self):
        """Default behavior is retry (mode='correct')."""
        kb = _make_kb()

        call_count = 0
        def improving_llm(prompt):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return "The company is in Chiang Mai."
            return "The company is in Bangkok."

        result = generate_with_guard(
            prompt="Where is the company?",
            kb=kb,
            llm_generate=improving_llm,
            axiom_claims=[Claim(subject="company", relation="location", object="Bangkok")],
            # mode not specified — should default to "correct"
        )

        assert result.status == "corrected"
        assert result.attempts == 2
        assert call_count == 2

    def test_explicit_correct_mode(self):
        """Explicit mode='correct' behaves same as default."""
        kb = _make_kb()

        call_count = 0
        def improving_llm(prompt):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return "The company is in Chiang Mai."
            return "The company is in Bangkok."

        result = generate_with_guard(
            prompt="test",
            kb=kb,
            llm_generate=improving_llm,
            axiom_claims=[Claim(subject="company", relation="location", object="Bangkok")],
            mode="correct",
        )

        assert result.status == "corrected"
        assert call_count == 2


# =====================================================================
# Phase 3: Structured Input Path (verify_structured)
# =====================================================================


class TestVerifyStructuredWithClaims:
    """verify_structured() with Claim objects — bypasses LLM extraction."""

    def test_passing_claims(self):
        """Valid claims pass verification."""
        kb = _make_kb()

        result = verify_structured(
            response_claims=[
                Claim(subject="patient", relation="takes", object="Warfarin"),
            ],
            kb=kb,
        )

        assert not result.is_hallucinating

    def test_violating_claims(self):
        """Claims that violate exclusion rule are caught."""
        kb = _make_kb()

        result = verify_structured(
            response_claims=[
                Claim(subject="patient", relation="takes", object="Aspirin"),
            ],
            axiom_claims=[
                Claim(subject="patient", relation="takes", object="Warfarin"),
            ],
            kb=kb,
        )

        assert result.is_hallucinating
        assert result.violated_rules
        assert "drug_interaction" in str(result.violated_rules)

    def test_unique_rule_violation(self):
        """Two different blood types for same patient → UNSAT."""
        kb = _make_kb()

        result = verify_structured(
            response_claims=[
                Claim(subject="patient", relation="blood_type", object="A"),
            ],
            axiom_claims=[
                Claim(subject="patient", relation="blood_type", object="O"),
            ],
            kb=kb,
        )

        assert result.is_hallucinating


class TestVerifyStructuredWithDicts:
    """verify_structured() with plain dicts — JSON API compatible."""

    def test_dict_claims_pass(self):
        """Dict-based claims work identically to Claim objects."""
        kb = _make_kb()

        result = verify_structured(
            response_claims=[
                {"subject": "patient", "relation": "takes", "object": "Warfarin"},
            ],
            kb=kb,
        )

        assert not result.is_hallucinating

    def test_dict_claims_violation(self):
        """Dict-based claims caught by exclusion rule."""
        kb = _make_kb()

        result = verify_structured(
            response_claims=[
                {"subject": "patient", "relation": "takes", "object": "Aspirin"},
            ],
            axiom_claims=[
                {"subject": "patient", "relation": "takes", "object": "Warfarin"},
            ],
            kb=kb,
        )

        assert result.is_hallucinating

    def test_mixed_claims_and_dicts(self):
        """Can mix Claim objects and dicts in the same call."""
        kb = _make_kb()

        result = verify_structured(
            response_claims=[
                Claim(subject="patient", relation="takes", object="Aspirin"),
            ],
            axiom_claims=[
                {"subject": "patient", "relation": "takes", "object": "Warfarin"},
            ],
            kb=kb,
        )

        assert result.is_hallucinating

    def test_dict_with_negated(self):
        """Dict with negated=True is handled."""
        kb = _make_kb()

        result = verify_structured(
            response_claims=[
                {"subject": "patient", "relation": "takes", "object": "Aspirin", "negated": True},
            ],
            kb=kb,
        )

        assert not result.is_hallucinating  # Negated claim, no conflict


class TestVerifyStructuredErrors:
    """Error handling for verify_structured()."""

    def test_missing_keys_raises(self):
        """Dict missing required keys raises ValueError."""
        kb = _make_kb()

        with pytest.raises(ValueError, match="missing required keys"):
            verify_structured(
                response_claims=[
                    {"subject": "patient"},  # Missing relation and object
                ],
                kb=kb,
            )

    def test_wrong_type_raises(self):
        """Non-Claim, non-dict input raises ValueError."""
        kb = _make_kb()

        with pytest.raises(ValueError, match="must be a Claim object or dict"):
            verify_structured(
                response_claims=["just a string"],
                kb=kb,
            )

    def test_no_kb_raises(self):
        """No KnowledgeBase loaded or provided raises RuntimeError."""
        import axiomguard.core as _core
        old_kb = _core._knowledge_base
        _core._knowledge_base = None
        try:
            with pytest.raises(RuntimeError, match="No KnowledgeBase"):
                verify_structured(
                    response_claims=[
                        Claim(subject="x", relation="y", object="z"),
                    ],
                )
        finally:
            _core._knowledge_base = old_kb


class TestVerifyStructuredWithTemporalRules:
    """verify_structured() with temporal rules and system_time."""

    def test_temporal_with_system_time(self):
        """Structured claims work with temporal rules."""
        kb = KnowledgeBase()
        kb.load_string("""
axiomguard: "0.3"
domain: medical
rules:
  - name: review_timeout
    type: temporal
    entity: patient
    relation: last_review_time
    max_delta: "4h"
    severity: error
    message: "Review overdue."
""")

        # 5 hours ago → UNSAT
        result = verify_structured(
            response_claims=[
                {"subject": "patient_1", "relation": "last_review_time", "object": "982000"},
            ],
            kb=kb,
            system_time=1000000,
        )

        assert result.is_hallucinating
        assert "review_timeout" in str(result.violated_rules)

    def test_temporal_within_limit(self):
        """Within time limit → SAT."""
        kb = KnowledgeBase()
        kb.load_string("""
axiomguard: "0.3"
domain: medical
rules:
  - name: review_timeout
    type: temporal
    entity: patient
    relation: last_review_time
    max_delta: "4h"
    severity: error
    message: "Review overdue."
""")

        # 2 hours ago → SAT
        result = verify_structured(
            response_claims=[
                Claim(subject="patient_1", relation="last_review_time", object="992800"),
            ],
            kb=kb,
            system_time=1000000,
        )

        assert not result.is_hallucinating


class TestVerifyStructuredEntityResolution:
    """Entity resolution works with structured input."""

    def test_aliases_resolved(self):
        """Entity aliases from YAML are applied to structured claims."""
        kb = _make_kb()

        # "pt" is an alias for "patient" in our rules
        result = verify_structured(
            response_claims=[
                Claim(subject="pt", relation="blood_type", object="A"),
            ],
            axiom_claims=[
                Claim(subject="patient", relation="blood_type", object="O"),
            ],
            kb=kb,
        )

        # Should resolve "pt" → "patient" and detect unique violation
        assert result.is_hallucinating
