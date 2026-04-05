"""
Tests for v0.7.0 — Axiom Studio core logic.

Tests the pure logic layer without requiring Streamlit.
"""

import yaml

from axiomguard.studio.core import (
    StudioState,
    add_rule_to_state,
    build_yaml_output,
    remove_rule_from_state,
    verify_claim_against_rules,
    validate_yaml_input,
)


# =====================================================================
# StudioState
# =====================================================================


class TestStudioState:

    def test_default_state(self):
        state = StudioState()
        assert state.domain == "my_domain"
        assert state.rules == []

    def test_add_rule(self):
        state = StudioState()
        add_rule_to_state(state, {"name": "r1", "type": "unique"})
        assert len(state.rules) == 1

    def test_remove_rule(self):
        state = StudioState(rules=[{"name": "r1"}, {"name": "r2"}])
        remove_rule_from_state(state, 0)
        assert len(state.rules) == 1
        assert state.rules[0]["name"] == "r2"

    def test_remove_out_of_bounds(self):
        state = StudioState(rules=[{"name": "r1"}])
        remove_rule_from_state(state, 5)  # Should not crash
        assert len(state.rules) == 1


# =====================================================================
# YAML Output
# =====================================================================


class TestBuildYaml:

    def test_empty_rules(self):
        output = build_yaml_output("test", [])
        assert "axiomguard" in output
        assert "test" in output

    def test_single_rule(self):
        rules = [{
            "name": "max_age",
            "type": "range",
            "entity": "person",
            "relation": "age",
            "value_type": "int",
            "max": 120,
            "severity": "error",
            "message": "Age must be <= 120.",
        }]
        output = build_yaml_output("demo", rules)
        parsed = yaml.safe_load(output)
        assert parsed["domain"] == "demo"
        assert len(parsed["rules"]) == 1
        assert parsed["rules"][0]["name"] == "max_age"

    def test_none_values_stripped(self):
        rules = [{"name": "r1", "type": "unique", "entity": "x",
                  "relation": "y", "min": None, "max": None}]
        output = build_yaml_output("test", rules)
        parsed = yaml.safe_load(output)
        assert "min" not in parsed["rules"][0]
        assert "max" not in parsed["rules"][0]

    def test_multiple_rules(self):
        rules = [
            {"name": "r1", "type": "unique", "entity": "x", "relation": "y",
             "severity": "error", "message": "M1"},
            {"name": "r2", "type": "unique", "entity": "x", "relation": "z",
             "severity": "error", "message": "M2"},
        ]
        output = build_yaml_output("test", rules)
        parsed = yaml.safe_load(output)
        assert len(parsed["rules"]) == 2


# =====================================================================
# YAML Validation
# =====================================================================


class TestValidateYaml:

    def test_valid_yaml(self):
        yaml_str = """
axiomguard: "0.7"
domain: test
rules:
  - name: hq
    type: unique
    entity: company
    relation: location
    severity: error
    message: "Unique HQ."
"""
        result = validate_yaml_input(yaml_str)
        assert result["valid"] is True
        assert len(result["rules"]) == 1
        assert result["domain"] == "test"

    def test_invalid_yaml(self):
        result = validate_yaml_input("not: valid: yaml: [[[")
        assert result["valid"] is False, "Should reject malformed YAML"
        assert result["error"] is not None

    def test_empty_rules(self):
        result = validate_yaml_input("axiomguard: '0.7'\ndomain: x\nrules: []")
        # Empty rules should fail validation (min_length=1 on RuleSet.rules)
        assert result["valid"] is False


# =====================================================================
# Claim Testing
# =====================================================================


class TestClaimTesting:

    def test_passing_claim(self):
        yaml_str = """
axiomguard: "0.7"
domain: test
rules:
  - name: max_age
    type: range
    entity: person
    relation: age
    value_type: int
    max: 120
    severity: error
    message: "Age must be <= 120."
"""
        result = verify_claim_against_rules(yaml_str, "person", "age", "30")
        assert result["is_hallucinating"] is False

    def test_failing_claim(self):
        yaml_str = """
axiomguard: "0.7"
domain: test
rules:
  - name: max_age
    type: range
    entity: person
    relation: age
    value_type: int
    max: 120
    severity: error
    message: "Age must be <= 120."
"""
        result = verify_claim_against_rules(yaml_str, "person", "age", "999")
        assert result["is_hallucinating"] is True

    def test_invalid_yaml_returns_error(self):
        result = verify_claim_against_rules("invalid yaml", "x", "y", "z")
        assert "Error" in result["reason"] or not result["is_hallucinating"]

    def test_negation_rule(self):
        yaml_str = """
axiomguard: "0.7"
domain: test
rules:
  - name: no_banned
    type: negation
    entity: item
    relation: status
    must_not_include: banned
    severity: error
    message: "Item is banned."
"""
        r = verify_claim_against_rules(yaml_str, "item", "status", "banned")
        assert r["is_hallucinating"] is True

        r2 = verify_claim_against_rules(yaml_str, "item", "status", "approved")
        assert r2["is_hallucinating"] is False
