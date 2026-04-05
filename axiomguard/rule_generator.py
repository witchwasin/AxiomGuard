"""
AxiomGuard Rule Generator — Auto-generate .axiom.yml from documents.

Three modes of rule creation:

  Mode 1: Manual — write YAML by hand (already supported via KnowledgeBase.load)
  Mode 2: AI-Generated — send natural language policy to LLM, get YAML back
  Mode 3: Dynamic — build rules programmatically via RuleBuilder

Usage (Mode 2 — AI-Generated):

    from axiomguard.rule_generator import generate_rules

    yaml_str = generate_rules(
        text="บริษัทตั้งอยู่ที่กรุงเทพ CEO คือ สมชาย อายุงานขั้นต่ำ 6 เดือน",
        domain="company_policy",
    )
    # Returns valid .axiom.yml string

Usage (Mode 3 — Dynamic):

    from axiomguard.rule_generator import RuleBuilder

    builder = RuleBuilder(domain="loan_approval")
    builder.unique("hq_location", entity="company", relation="location", value="Bangkok")
    builder.range_rule("min_salary", entity="applicant", relation="salary", min=15000)

    kb = builder.to_knowledge_base()
"""

from __future__ import annotations

import json
import logging
import re
from pathlib import Path
from typing import Any, Callable, Optional

import yaml

from axiomguard.knowledge_base import KnowledgeBase


# =====================================================================
# SYSTEM PROMPT for Rule Generation (Mode 2)
# =====================================================================

_RULE_GEN_PROMPT = """\
You are an AxiomGuard Rule Compiler. Your job is to read a natural language \
document (policy, contract, regulation, or business rules) and extract ALL \
verifiable constraints as a valid AxiomGuard YAML rule file.

## Output Format (STRICT)

Return ONLY valid YAML — no markdown fences, no explanation, no preamble.

```
axiomguard: "0.3"
domain: <domain_name>

entities:
  - name: <entity>
    aliases: [<alias1>, <alias2>]

rules:
  - name: <rule_name_snake_case>
    type: <unique|exclusion|dependency|range>
    ... (type-specific fields)
    severity: error
    message: "<human-readable description of what this rule enforces>"
```

## Rule Types

### unique — an entity can only have ONE value for a relation
```yaml
- name: one_headquarters
  type: unique
  entity: company
  relation: location
  value: Bangkok
  severity: error
  message: "Company HQ is Bangkok only."
```

### exclusion — these values CANNOT coexist for the same entity
```yaml
- name: drug_interaction
  type: exclusion
  entity: patient
  relation: medication
  values: [Warfarin, Aspirin]
  severity: error
  message: "Warfarin and Aspirin cannot be prescribed together."
```

### dependency — if condition A is true, then B must also be true
```yaml
- name: min_employment
  type: dependency
  when:
    entity: applicant
    relation: employment_months
    value: "6"
    value_type: int
    operator: "<"
  then:
    require:
      relation: approval_status
      value: rejected
  severity: error
  message: "Applicant must have >= 6 months employment."
```

### range — a numeric value must be within bounds
```yaml
- name: salary_floor
  type: range
  entity: applicant
  relation: salary
  value_type: int
  min: 15000
  severity: error
  message: "Minimum salary is 15,000 THB."
```

## Extraction Rules

1. Extract EVERY verifiable constraint — even if implicit.
2. Use descriptive snake_case names for rules.
3. Include Thai or original-language text in `message` if the source is non-English.
4. Detect entities and create alias lists (e.g., "applicant" → ["ผู้กู้", "ลูกค้า"]).
5. Choose the most specific rule type for each constraint.
6. If unsure between types, prefer `unique` for single-value facts and `dependency` for conditional logic.
7. Numeric thresholds → use `range` or `dependency` with value_type.
8. Mutually exclusive options → use `exclusion`.
"""


# =====================================================================
# Mode 2: AI-Generated Rules
# =====================================================================


def generate_rules(
    text: str,
    domain: str = "auto_generated",
    llm_generate: Callable[[str], str] | None = None,
    model: str | None = None,
) -> str:
    """Generate .axiom.yml rules from a natural language document.

    Args:
        text: Natural language policy, contract, or business rules.
        domain: Domain name for the generated rule file.
        llm_generate: A callable (str) -> str that calls an LLM.
                      If None, tries Anthropic or OpenAI from environment.
        model: Optional model name override for the default backend.

    Returns:
        A valid .axiom.yml YAML string.

    Raises:
        RuntimeError: If no LLM backend is available.
        ValueError: If the LLM output is not valid YAML.

    Example::

        yaml_str = generate_rules(
            text=\"\"\"
            นโยบายสินเชื่อส่วนบุคคล:
            1. ผู้กู้ต้องมีอายุ 20-60 ปี
            2. เงินเดือนขั้นต่ำ 15,000 บาท
            3. อายุงานขั้นต่ำ 6 เดือน
            4. ห้ามมีประวัติค้างชำระ
            \"\"\",
            domain="personal_loan",
        )
    """
    generate_fn = llm_generate or _get_default_llm(model)

    prompt = (
        f"{_RULE_GEN_PROMPT}\n\n"
        f"## Domain\n{domain}\n\n"
        f"## Source Document\n\n{text}\n\n"
        f"Generate the .axiom.yml file now. Return ONLY valid YAML."
    )

    raw = generate_fn(prompt)
    yaml_str = _clean_yaml_output(raw)
    _validate_yaml(yaml_str)
    return yaml_str


def generate_rules_to_file(
    text: str,
    output_path: str | Path,
    domain: str = "auto_generated",
    llm_generate: Callable[[str], str] | None = None,
    model: str | None = None,
) -> Path:
    """Generate rules and save directly to a .axiom.yml file.

    Args:
        text: Natural language document.
        output_path: Where to save the YAML file.
        domain: Domain name.
        llm_generate: LLM callable.
        model: Optional model override.

    Returns:
        Path to the saved file.
    """
    yaml_str = generate_rules(text, domain, llm_generate, model)
    path = Path(output_path)
    path.write_text(yaml_str, encoding="utf-8")
    return path


def generate_rules_to_kb(
    text: str,
    domain: str = "auto_generated",
    llm_generate: Callable[[str], str] | None = None,
    model: str | None = None,
) -> KnowledgeBase:
    """Generate rules and load them directly into a KnowledgeBase.

    This is the fastest path from document to verification:

        kb = generate_rules_to_kb("Company HQ is Bangkok. CEO is Somchai.")
        result = kb.verify(claims)

    Args:
        text: Natural language document.
        domain: Domain name.
        llm_generate: LLM callable.
        model: Optional model override.

    Returns:
        A ready-to-use KnowledgeBase with the generated rules loaded.
    """
    yaml_str = generate_rules(text, domain, llm_generate, model)
    kb = KnowledgeBase()
    kb.load_string(yaml_str)
    return kb


# =====================================================================
# Mode 3: Dynamic / Programmatic Rules (RuleBuilder)
# =====================================================================


class RuleBuilder:
    """Fluent API for building rules programmatically.

    Example::

        builder = RuleBuilder(domain="hr_policy")

        builder.unique("one_department", entity="employee", relation="department")

        builder.exclusion(
            "leave_conflict",
            entity="employee",
            relation="leave_type",
            values=["sick_leave", "vacation"],
            message="Cannot take sick leave and vacation on the same day.",
        )

        builder.range_rule(
            "age_limit",
            entity="applicant",
            relation="age",
            min=20, max=60,
            message="Applicant must be 20-60 years old.",
        )

        builder.dependency(
            "probation_review",
            when={"entity": "employee", "relation": "months_employed",
                  "value": "3", "value_type": "int", "operator": "<"},
            then_require={"relation": "status", "value": "probation"},
            message="Employees under 3 months must be on probation.",
        )

        # Get YAML string
        yaml_str = builder.to_yaml()

        # Or load directly into a KnowledgeBase
        kb = builder.to_knowledge_base()

        # Or add rules dynamically from a database
        for row in db.query("SELECT * FROM policies WHERE country = 'TH'"):
            builder.unique(row.name, entity=row.entity,
                          relation=row.relation, value=row.value)
    """

    def __init__(self, domain: str = "dynamic", version: str = "0.3") -> None:
        self._domain = domain
        self._version = version
        self._entities: list[dict[str, Any]] = []
        self._rules: list[dict[str, Any]] = []

    def entity(
        self,
        name: str,
        aliases: list[str] | None = None,
        description: str = "",
    ) -> "RuleBuilder":
        """Register an entity with optional aliases."""
        self._entities.append({
            "name": name,
            "aliases": aliases or [],
            **({"description": description} if description else {}),
        })
        return self

    def unique(
        self,
        name: str,
        *,
        entity: str,
        relation: str,
        value: str | None = None,
        severity: str = "error",
        message: str = "",
    ) -> "RuleBuilder":
        """Add a unique (single-value) rule."""
        rule: dict[str, Any] = {
            "name": name,
            "type": "unique",
            "entity": entity,
            "relation": relation,
            "severity": severity,
        }
        if value is not None:
            rule["value"] = value
        if message:
            rule["message"] = message
        self._rules.append(rule)
        return self

    def exclusion(
        self,
        name: str,
        *,
        entity: str,
        relation: str,
        values: list[str],
        severity: str = "error",
        message: str = "",
    ) -> "RuleBuilder":
        """Add an exclusion (mutual conflict) rule."""
        self._rules.append({
            "name": name,
            "type": "exclusion",
            "entity": entity,
            "relation": relation,
            "values": values,
            "severity": severity,
            **({"message": message} if message else {}),
        })
        return self

    def dependency(
        self,
        name: str,
        *,
        when: dict[str, Any],
        then_require: dict[str, Any],
        severity: str = "error",
        message: str = "",
    ) -> "RuleBuilder":
        """Add a dependency (if-then) rule.

        Args:
            when: Dict with keys: entity, relation, value,
                  and optionally operator, value_type.
            then_require: Dict with keys: relation, value,
                          and optionally operator, value_type.
        """
        self._rules.append({
            "name": name,
            "type": "dependency",
            "when": when,
            "then": {"require": then_require},
            "severity": severity,
            **({"message": message} if message else {}),
        })
        return self

    def range_rule(
        self,
        name: str,
        *,
        entity: str,
        relation: str,
        min: float | int | None = None,
        max: float | int | None = None,
        value_type: str = "int",
        severity: str = "error",
        message: str = "",
    ) -> "RuleBuilder":
        """Add a range (numeric bounds) rule."""
        rule: dict[str, Any] = {
            "name": name,
            "type": "range",
            "entity": entity,
            "relation": relation,
            "value_type": value_type,
            "severity": severity,
        }
        if min is not None:
            rule["min"] = min
        if max is not None:
            rule["max"] = max
        if message:
            rule["message"] = message
        self._rules.append(rule)
        return self

    def to_yaml(self) -> str:
        """Export rules as a .axiom.yml YAML string."""
        data: dict[str, Any] = {
            "axiomguard": self._version,
            "domain": self._domain,
        }
        if self._entities:
            data["entities"] = self._entities
        data["rules"] = self._rules
        return yaml.dump(data, allow_unicode=True, sort_keys=False, default_flow_style=False)

    def to_file(self, path: str | Path) -> Path:
        """Export rules to a .axiom.yml file."""
        p = Path(path)
        p.write_text(self.to_yaml(), encoding="utf-8")
        return p

    def to_knowledge_base(self) -> KnowledgeBase:
        """Load rules directly into a KnowledgeBase ready for verification."""
        kb = KnowledgeBase()
        kb.load_string(self.to_yaml())
        return kb

    @property
    def rule_count(self) -> int:
        return len(self._rules)


# =====================================================================
# Internal Helpers
# =====================================================================


def _clean_yaml_output(raw: str) -> str:
    """Clean LLM output to extract valid YAML."""
    text = raw.strip()

    # Strip markdown fences
    if text.startswith("```"):
        text = re.sub(r"^```(?:ya?ml)?\s*\n?", "", text)
        text = re.sub(r"\n?```\s*$", "", text)
        text = text.strip()

    return text


def _validate_yaml(yaml_str: str) -> None:
    """Validate that the YAML is parseable and has required structure."""
    try:
        data = yaml.safe_load(yaml_str)
    except yaml.YAMLError as e:
        raise ValueError(f"Generated YAML is not valid: {e}") from e

    if not isinstance(data, dict):
        raise ValueError("Generated YAML must be a mapping (dict)")
    if "rules" not in data:
        raise ValueError("Generated YAML must contain a 'rules' key")
    if not isinstance(data["rules"], list) or len(data["rules"]) == 0:
        raise ValueError("Generated YAML must contain at least one rule")


def _get_default_llm(model: str | None = None) -> Callable[[str], str]:
    """Try to find a working LLM backend from environment."""
    import os

    logger = logging.getLogger(__name__)

    # Try Anthropic first
    if os.environ.get("ANTHROPIC_API_KEY"):
        try:
            import anthropic

            client = anthropic.Anthropic()
            model_name = model or "claude-haiku-4-5-20251001"

            def _anthropic_generate(prompt: str) -> str:
                response = client.messages.create(
                    model=model_name,
                    max_tokens=4096,
                    messages=[{"role": "user", "content": prompt}],
                )
                return response.content[0].text

            return _anthropic_generate
        except ImportError:
            logger.debug("anthropic package not installed, trying openai")

    # Try OpenAI
    if os.environ.get("OPENAI_API_KEY"):
        try:
            import openai

            client = openai.OpenAI()
            model_name = model or "gpt-4o-mini"

            def _openai_generate(prompt: str) -> str:
                response = client.chat.completions.create(
                    model=model_name,
                    messages=[{"role": "user", "content": prompt}],
                    max_tokens=4096,
                )
                return response.choices[0].message.content

            return _openai_generate
        except ImportError:
            logger.debug("openai package not installed, no LLM backends available")

    raise RuntimeError(
        "No LLM backend available for rule generation. Either:\n"
        "  1. Set ANTHROPIC_API_KEY and `pip install anthropic`\n"
        "  2. Set OPENAI_API_KEY and `pip install openai`\n"
        "  3. Pass a custom llm_generate function"
    )
