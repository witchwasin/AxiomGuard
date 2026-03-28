"""Tests for axiomguard.rule_generator — RuleBuilder and generate_rules."""

import pytest
import yaml

from axiomguard.rule_generator import RuleBuilder, generate_rules, _clean_yaml_output, _validate_yaml


# =====================================================================
# RuleBuilder (Mode 3: Dynamic)
# =====================================================================


class TestRuleBuilder:
    """Test the fluent programmatic rule builder."""

    def test_unique_rule(self):
        builder = RuleBuilder(domain="test")
        builder.unique("hq_location", entity="company", relation="location", value="Bangkok")

        yaml_str = builder.to_yaml()
        data = yaml.safe_load(yaml_str)

        assert data["domain"] == "test"
        assert len(data["rules"]) == 1
        assert data["rules"][0]["type"] == "unique"
        assert data["rules"][0]["relation"] == "location"

    def test_exclusion_rule(self):
        builder = RuleBuilder(domain="medical")
        builder.exclusion(
            "drug_conflict",
            entity="patient",
            relation="medication",
            values=["Warfarin", "Aspirin"],
            message="Cannot prescribe together.",
        )

        data = yaml.safe_load(builder.to_yaml())
        rule = data["rules"][0]
        assert rule["type"] == "exclusion"
        assert rule["values"] == ["Warfarin", "Aspirin"]
        assert rule["message"] == "Cannot prescribe together."

    def test_range_rule(self):
        builder = RuleBuilder(domain="hr")
        builder.range_rule(
            "age_limit",
            entity="applicant",
            relation="age",
            min=20,
            max=60,
            message="Must be 20-60 years old.",
        )

        data = yaml.safe_load(builder.to_yaml())
        rule = data["rules"][0]
        assert rule["type"] == "range"
        assert rule["min"] == 20
        assert rule["max"] == 60

    def test_dependency_rule(self):
        builder = RuleBuilder(domain="loan")
        builder.dependency(
            "min_employment",
            when={"entity": "applicant", "relation": "employment_months",
                  "value": "6", "value_type": "int", "operator": "<"},
            then_require={"relation": "approval_status", "value": "rejected"},
            message="Need >= 6 months employment.",
        )

        data = yaml.safe_load(builder.to_yaml())
        rule = data["rules"][0]
        assert rule["type"] == "dependency"
        assert rule["when"]["operator"] == "<"
        assert rule["then"]["require"]["value"] == "rejected"

    def test_entity_registration(self):
        builder = RuleBuilder(domain="test")
        builder.entity("applicant", aliases=["ผู้กู้", "client"])
        builder.unique("test_rule", entity="applicant", relation="name")

        data = yaml.safe_load(builder.to_yaml())
        assert data["entities"][0]["name"] == "applicant"
        assert "ผู้กู้" in data["entities"][0]["aliases"]

    def test_fluent_chaining(self):
        builder = (
            RuleBuilder(domain="chained")
            .entity("company")
            .unique("r1", entity="company", relation="location")
            .unique("r2", entity="company", relation="ceo")
            .range_rule("r3", entity="company", relation="revenue", min=0)
        )

        assert builder.rule_count == 3

    def test_to_knowledge_base(self):
        builder = RuleBuilder(domain="test")
        builder.unique("hq", entity="company", relation="location")

        kb = builder.to_knowledge_base()
        assert kb.rule_count == 1
        assert kb.constraint_count >= 1

    def test_to_file(self, tmp_path):
        builder = RuleBuilder(domain="file_test")
        builder.unique("r1", entity="e", relation="r")

        path = builder.to_file(tmp_path / "test.axiom.yml")
        assert path.exists()

        content = path.read_text()
        data = yaml.safe_load(content)
        assert data["domain"] == "file_test"

    def test_empty_builder_raises(self):
        builder = RuleBuilder(domain="empty")
        yaml_str = builder.to_yaml()
        data = yaml.safe_load(yaml_str)
        # Empty rules list — will fail Pydantic validation when loaded into KB
        assert data["rules"] == []

    def test_dynamic_from_data(self):
        """Simulate building rules from database rows."""
        db_rows = [
            {"name": "r1", "entity": "user", "relation": "country", "value": "TH"},
            {"name": "r2", "entity": "user", "relation": "language", "value": "Thai"},
        ]

        builder = RuleBuilder(domain="dynamic_db")
        for row in db_rows:
            builder.unique(row["name"], entity=row["entity"],
                          relation=row["relation"], value=row["value"])

        assert builder.rule_count == 2
        kb = builder.to_knowledge_base()
        assert kb.rule_count == 2


# =====================================================================
# AI Generation Helpers
# =====================================================================


class TestYamlCleaning:
    """Test YAML output cleaning from LLM responses."""

    def test_clean_plain_yaml(self):
        raw = 'axiomguard: "0.3"\nrules:\n  - name: test\n    type: unique\n    entity: e\n    relation: r'
        assert _clean_yaml_output(raw) == raw

    def test_strip_markdown_fences(self):
        raw = '```yaml\naxiomguard: "0.3"\nrules:\n  - name: test\n    type: unique\n    entity: e\n    relation: r\n```'
        cleaned = _clean_yaml_output(raw)
        assert not cleaned.startswith("```")
        assert not cleaned.endswith("```")
        assert 'axiomguard: "0.3"' in cleaned

    def test_strip_yml_fences(self):
        raw = '```yml\naxiomguard: "0.3"\nrules:\n  - name: t\n    type: unique\n    entity: e\n    relation: r\n```'
        cleaned = _clean_yaml_output(raw)
        assert 'axiomguard' in cleaned

    def test_validate_yaml_valid(self):
        yaml_str = 'axiomguard: "0.3"\nrules:\n  - name: t\n    type: unique\n    entity: e\n    relation: r'
        _validate_yaml(yaml_str)  # Should not raise

    def test_validate_yaml_no_rules(self):
        with pytest.raises(ValueError, match="rules"):
            _validate_yaml('axiomguard: "0.3"\nentities: []')

    def test_validate_yaml_empty_rules(self):
        with pytest.raises(ValueError, match="at least one rule"):
            _validate_yaml('axiomguard: "0.3"\nrules: []')

    def test_validate_yaml_invalid(self):
        with pytest.raises(ValueError):
            _validate_yaml(":::invalid yaml{{{}}")


# =====================================================================
# AI Generation (Mode 2) — with mock LLM
# =====================================================================


class TestGenerateRules:
    """Test generate_rules with a mock LLM backend."""

    def _mock_llm(self, prompt: str) -> str:
        """Mock LLM that returns valid YAML for any prompt."""
        return """\
axiomguard: "0.3"
domain: mock_domain

entities:
  - name: company
    aliases: ["firm", "org"]

rules:
  - name: hq_location
    type: unique
    entity: company
    relation: location
    value: Bangkok
    severity: error
    message: "HQ is Bangkok."
"""

    def test_generate_with_mock(self):
        yaml_str = generate_rules(
            text="Company is in Bangkok",
            domain="test",
            llm_generate=self._mock_llm,
        )
        data = yaml.safe_load(yaml_str)
        assert data["rules"][0]["name"] == "hq_location"

    def test_generate_with_fenced_mock(self):
        def fenced_llm(prompt: str) -> str:
            return "```yaml\n" + self._mock_llm(prompt) + "\n```"

        yaml_str = generate_rules(
            text="test", domain="test", llm_generate=fenced_llm,
        )
        data = yaml.safe_load(yaml_str)
        assert len(data["rules"]) >= 1

    def test_generate_invalid_llm_output(self):
        def bad_llm(prompt: str) -> str:
            return "Sorry, I can't help with that."

        with pytest.raises(ValueError):
            generate_rules(text="test", domain="test", llm_generate=bad_llm)

    def test_no_llm_available_raises(self, monkeypatch):
        monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
        monkeypatch.delenv("OPENAI_API_KEY", raising=False)

        with pytest.raises(RuntimeError, match="No LLM backend"):
            generate_rules(text="test", domain="test")


# =====================================================================
# Integration: RuleBuilder → KnowledgeBase → Verify
# =====================================================================


class TestBuilderToVerification:
    """End-to-end: build rules dynamically, then verify claims."""

    def test_unique_rule_catches_contradiction(self):
        from axiomguard.models import Claim

        kb = (
            RuleBuilder(domain="e2e")
            .unique("hq", entity="company", relation="location")
            .to_knowledge_base()
        )

        axioms = [Claim(subject="company", relation="location", object="Bangkok")]
        response = [Claim(subject="company", relation="location", object="Chiang Mai")]

        result = kb.verify(response, axioms)
        assert result.is_hallucinating is True

    def test_unique_rule_passes_correct(self):
        from axiomguard.models import Claim

        kb = (
            RuleBuilder(domain="e2e")
            .unique("hq", entity="company", relation="location")
            .to_knowledge_base()
        )

        axioms = [Claim(subject="company", relation="location", object="Bangkok")]
        response = [Claim(subject="company", relation="location", object="Bangkok")]

        result = kb.verify(response, axioms)
        assert result.is_hallucinating is False

    def test_range_rule_catches_violation(self):
        from axiomguard.models import Claim

        kb = (
            RuleBuilder(domain="e2e")
            .range_rule("min_salary", entity="applicant",
                       relation="salary", min=15000, value_type="int")
            .to_knowledge_base()
        )

        response = [Claim(subject="applicant", relation="salary", object="10000")]
        result = kb.verify(response)
        assert result.is_hallucinating is True
