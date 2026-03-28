"""
AxiomGuard Parser — YAML Rule Loader & Validator

Reads `.axiom.yml` files and converts them into validated Pydantic models.
Each rule type (unique, exclusion, dependency) has its own model with
strict validation so errors are caught at load time, not at Z3 time.

Usage:
    from axiomguard.parser import AxiomParser

    parser = AxiomParser()
    ruleset = parser.load("rules/medical.axiom.yml")
    # ruleset.rules → list of UniqueRule | ExclusionRule | DependencyRule
"""

from __future__ import annotations

from pathlib import Path
from typing import Annotated, List, Literal, Optional, Union

import yaml
from pydantic import BaseModel, Field


# =====================================================================
# Sub-Models
# =====================================================================


class EntityDef(BaseModel):
    """Entity definition with optional aliases for EntityResolver integration."""

    name: str = Field(min_length=1)
    aliases: list[str] = Field(default_factory=list)
    description: str = ""


class TestExample(BaseModel):
    """Inline test case embedded in a rule for self-testing."""

    input: str
    axioms: list[str] = Field(default_factory=list)
    expect: Literal["pass", "fail"]
    description: str = ""


# =====================================================================
# Rule Types
# =====================================================================


class _RuleBase(BaseModel):
    """Shared fields across all rule types."""

    name: str = Field(min_length=1)
    description: str = ""
    severity: Literal["error", "warning", "info"] = "error"
    message: str = ""
    examples: list[TestExample] = Field(default_factory=list)


class UniqueRule(_RuleBase):
    """Cardinality rule: an entity can only have ONE value for this relation.

    Example YAML:
        - name: One headquarters per company
          type: unique
          entity: company
          relation: headquarters
    """

    type: Literal["unique"]
    entity: str = Field(min_length=1)
    relation: str = Field(min_length=1)


class ExclusionRule(_RuleBase):
    """Conflict rule: these specific values cannot coexist for the same entity.

    Example YAML:
        - name: Warfarin-Aspirin interaction
          type: exclusion
          entity: patient
          relation: takes
          values: [Warfarin, Aspirin]
    """

    type: Literal["exclusion"]
    entity: str = Field(min_length=1)
    relation: str = Field(min_length=1)
    values: list[str] = Field(min_length=2)


class WhenCondition(BaseModel):
    """The 'if' part of a dependency rule."""

    entity: str = Field(min_length=1)
    relation: str = Field(min_length=1)
    value: str = Field(min_length=1)
    operator: str = "="
    value_type: Literal["string", "int", "float", "date"] = "string"


class ThenRequirement(BaseModel):
    """What must be true when the condition is met."""

    relation: str = Field(min_length=1)
    value: str = Field(min_length=1)
    operator: str = "="
    value_type: Literal["string", "int", "float", "date"] = "string"


class ThenClause(BaseModel):
    """The 'then' part of a dependency rule."""

    require: ThenRequirement


class DependencyRule(_RuleBase):
    """Implication rule: if condition A is true, then B must also be true.

    Example YAML:
        - name: Claim requires active policy
          type: dependency
          when:
            entity: claim
            relation: type
            value: insurance_claim
          then:
            require:
              relation: policy_status
              value: active
    """

    type: Literal["dependency"]
    when: WhenCondition
    then: ThenClause


class RangeRule(_RuleBase):
    """Bound rule: a numeric attribute must be within min/max.

    Example YAML:
        - name: Dosage within safe range
          type: range
          entity: prescription
          relation: dosage_mg
          value_type: int
          min: 0
          max: 500
    """

    type: Literal["range"]
    entity: str = Field(min_length=1)
    relation: str = Field(min_length=1)
    value_type: Literal["int", "float"] = "int"
    min: Optional[float] = None
    max: Optional[float] = None


# =====================================================================
# Discriminated Union
# =====================================================================

Rule = Annotated[
    Union[UniqueRule, ExclusionRule, DependencyRule, RangeRule],
    Field(discriminator="type"),
]


# =====================================================================
# Top-Level RuleSet
# =====================================================================


class RuleSet(BaseModel):
    """Top-level container for an .axiom.yml file."""

    axiomguard: str = Field(description="Format version (e.g., '0.3')")
    domain: str = ""
    entities: list[EntityDef] = Field(default_factory=list)
    rules: list[Rule] = Field(min_length=1)


# =====================================================================
# Shared Aliases File
# =====================================================================


class AliasFile(BaseModel):
    """Schema for _aliases.yml shared alias files."""

    axiomguard: str
    aliases: dict[str, list[str]]


# =====================================================================
# Parser
# =====================================================================


class AxiomParser:
    """Loads and validates .axiom.yml files.

    Usage::

        parser = AxiomParser()
        ruleset = parser.load("rules/medical.axiom.yml")

        for rule in ruleset.rules:
            print(f"{rule.name} ({rule.type})")
    """

    def load(self, path: str | Path) -> RuleSet:
        """Load and validate an .axiom.yml file.

        Args:
            path: Path to the YAML file.

        Returns:
            Validated RuleSet.

        Raises:
            FileNotFoundError: If the file doesn't exist.
            yaml.YAMLError: If the YAML is malformed.
            pydantic.ValidationError: If the content doesn't match the schema.
        """
        path = Path(path)
        with open(path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f)

        return RuleSet.model_validate(data)

    def load_string(self, content: str) -> RuleSet:
        """Load and validate from a YAML string (useful for testing).

        Args:
            content: YAML content as a string.

        Returns:
            Validated RuleSet.
        """
        data = yaml.safe_load(content)
        return RuleSet.model_validate(data)

    def load_aliases(self, path: str | Path) -> dict[str, list[str]]:
        """Load a shared _aliases.yml file.

        Args:
            path: Path to the aliases YAML file.

        Returns:
            Dict mapping canonical names to lists of aliases.
        """
        path = Path(path)
        with open(path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f)

        alias_file = AliasFile.model_validate(data)
        return alias_file.aliases
