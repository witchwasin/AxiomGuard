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

import re
from pathlib import Path
from typing import Annotated, List, Literal, Optional, Union

import yaml
from pydantic import BaseModel, Field, model_validator, field_validator


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
    """Shared fields across all rule types.

    The `message` field is the hardcoded error string returned verbatim
    when Z3 proves a violation. No LLM translates or paraphrases this —
    it is the exact text the human domain expert wrote.

    For error-severity rules, `message` should always be set. A warning
    is issued at parse time if it is missing.
    """

    name: str = Field(min_length=1)
    description: str = ""
    severity: Literal["error", "warning", "info"] = "error"
    message: str = Field(
        default="",
        description="Hardcoded error message returned verbatim on violation. "
        "No LLM involved — this is the exact string auditors will see.",
    )
    examples: list[TestExample] = Field(default_factory=list)

    @model_validator(mode="after")
    def warn_missing_message(self) -> "_RuleBase":
        if self.severity == "error" and not self.message:
            import warnings
            warnings.warn(
                f'Rule "{self.name}" has severity=error but no message. '
                f"Enterprise best practice: always set a hardcoded message "
                f"for deterministic error reporting.",
                UserWarning,
                stacklevel=2,
            )
        return self


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

    require: Optional[ThenRequirement] = None
    forbid: Optional["ThenForbid"] = None

    @model_validator(mode="after")
    def require_at_least_one(self) -> "ThenClause":
        if self.require is None and self.forbid is None:
            raise ValueError("ThenClause must have at least one of 'require' or 'forbid'.")
        return self


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
# Time Delta Parsing
# =====================================================================

_DELTA_MULTIPLIERS = {"s": 1, "m": 60, "h": 3600, "d": 86400, "w": 604800}


def parse_delta(delta_str: str) -> int:
    """Parse a human-readable time delta string to seconds.

    Supports: 30s, 5m, 4h, 7d, 2w (seconds, minutes, hours, days, weeks).

    Args:
        delta_str: Time delta string (e.g., "4h", "30m", "7d").

    Returns:
        Number of seconds.

    Raises:
        ValueError: If the format is not recognized.
    """
    match = re.match(r"^(\d+)\s*(s|m|h|d|w)$", delta_str.strip())
    if not match:
        raise ValueError(
            f"Invalid delta format: '{delta_str}'. "
            f"Expected: <number><unit> where unit is s/m/h/d/w "
            f"(e.g., '4h', '30m', '7d')"
        )
    value = int(match.group(1))
    unit = match.group(2)
    return value * _DELTA_MULTIPLIERS[unit]


class NegationRule(_RuleBase):
    """Prohibition rule: entity must NOT have these values.

    Example YAML (single):
        - name: No penicillin for allergic patients
          type: negation
          entity: patient
          relation: medication
          must_not_include: Penicillin
          message: "Patient must NOT receive Penicillin."

    Example YAML (multiple):
        - name: Banned substances
          type: negation
          entity: employee
          relation: substance_test
          must_not_include: [Methamphetamine, Cocaine, Heroin]
          message: "Banned substance detected."
    """

    type: Literal["negation"]
    entity: str = Field(min_length=1)
    relation: str = Field(min_length=1)
    must_not_include: list[str] = Field(min_length=1)

    @field_validator("must_not_include", mode="before")
    @classmethod
    def normalize_to_list(cls, v):
        if isinstance(v, str):
            return [v]
        return v


class ThenForbid(BaseModel):
    """What must NOT be true when the dependency condition is met."""

    relation: str = Field(min_length=1)
    values: list[str] = Field(min_length=1)


class TemporalRule(_RuleBase):
    """Time-bound constraint: enforces time delta between events or vs system clock.

    Z3 computes the delta mathematically — no LLM estimates passage of time.

    Example YAML (event vs system_time):
        - name: medication_review_overdue
          type: temporal
          entity: patient
          relation: last_review_time
          reference: system_time
          max_delta: "4h"
          message: "Medication review overdue — must be within 4 hours."

    Example YAML (event vs event):
        - name: min_hospital_stay
          type: temporal
          entity: patient
          relation: admission_time
          reference: discharge_time
          min_delta: "1h"
          message: "Patient must stay at least 1 hour."

    Example YAML (both bounds):
        - name: token_validity
          type: temporal
          entity: session
          relation: token_issued_at
          reference: system_time
          min_delta: "0s"
          max_delta: "1h"
          message: "Token must be valid (0-1 hour old)."
    """

    type: Literal["temporal"]
    entity: str = Field(min_length=1)
    relation: str = Field(
        min_length=1,
        description="The timestamp relation (e.g., 'last_review_time')",
    )
    reference: str = Field(
        default="system_time",
        description="What to compare against: 'system_time' or another relation name",
    )
    min_delta: Optional[str] = Field(
        default=None,
        description="Minimum required time difference (e.g., '1h', '30m')",
    )
    max_delta: Optional[str] = Field(
        default=None,
        description="Maximum allowed time difference (e.g., '4h', '7d')",
    )

    @field_validator("min_delta", "max_delta", mode="before")
    @classmethod
    def validate_delta_format(cls, v: Optional[str]) -> Optional[str]:
        if v is not None:
            parse_delta(v)  # Will raise ValueError if invalid
        return v

    @model_validator(mode="after")
    def require_at_least_one_delta(self) -> "TemporalRule":
        if self.min_delta is None and self.max_delta is None:
            raise ValueError(
                f'Temporal rule "{self.name}" must specify at least one of '
                f"min_delta or max_delta."
            )
        return self


# =====================================================================
# Discriminated Union
# =====================================================================

Rule = Annotated[
    Union[UniqueRule, ExclusionRule, DependencyRule, RangeRule, NegationRule, TemporalRule],
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
