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


class RelationDef(BaseModel):
    """Relation definition with classification metadata (v0.6.0).

    Categories (from Resnik 2025):
      - definitional: Stable facts that don't change with context.
        e.g., "a nurse is a healthcare worker"
      - contingent: True now but could change. Safe to use per norms.
        e.g., "nurses typically wear blue"
      - normative_risk: Statistically true but normatively unacceptable to use.
        e.g., "nurses are more likely to wear dresses"

    When a claim uses a normative_risk relation, audit_extraction_bias()
    can flag it for human review.
    """

    name: str = Field(min_length=1)
    category: Literal["definitional", "contingent", "normative_risk"] = "contingent"
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


_STRING_OPS = {"=", "!="}
_NUMERIC_OPS = {"=", "==", "!=", "<", ">", "<=", ">="}


class WhenCondition(BaseModel):
    """The 'if' part of a dependency rule."""

    entity: str = Field(min_length=1)
    relation: str = Field(min_length=1)
    value: str = Field(min_length=1)
    operator: str = "="
    value_type: Literal["string", "int", "float", "date"] = "string"

    @model_validator(mode="after")
    def validate_operator_for_type(self) -> "WhenCondition":
        valid = _NUMERIC_OPS if self.value_type != "string" else _STRING_OPS
        if self.operator not in valid:
            raise ValueError(
                f'Operator "{self.operator}" is not valid for value_type '
                f'"{self.value_type}". Valid: {valid}'
            )
        return self


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


class ChainStep(BaseModel):
    """One step in a conditional chain: when → then."""

    when: "ChainWhen"
    then: ThenClause


class ChainWhen(BaseModel):
    """Simplified when condition for chain steps (inherits entity from parent)."""

    relation: str = Field(min_length=1)
    value: str = Field(min_length=1)
    operator: str = "="
    value_type: Literal["string", "int", "float", "date"] = "string"


class DependencyRule(_RuleBase):
    """Implication rule: if condition A is true, then B must also be true.

    Supports optional chain for transitive dependencies: A → B → C.

    Example YAML (simple):
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

    Example YAML (chained):
        - name: Loan approval chain
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
    """

    type: Literal["dependency"]
    when: WhenCondition
    then: ThenClause
    chain: Optional[list[ChainStep]] = None


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

    @model_validator(mode="after")
    def validate_range_bounds(self) -> "RangeRule":
        if self.min is not None and self.max is not None:
            if self.min > self.max:
                raise ValueError(
                    f'RangeRule "{self.name}": min ({self.min}) cannot be '
                    f"greater than max ({self.max})"
                )
        return self


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
# v0.7.0 — Advanced Rule Types
# =====================================================================


class ComparisonOperand(BaseModel):
    """One side of a comparison rule (left or right)."""

    relation: str = Field(min_length=1)
    value_type: Literal["int", "float"] = "int"
    multiplier: Optional[float] = None


class ComparisonRule(_RuleBase):
    """Cross-relation arithmetic: compare two numeric attributes.

    Example YAML:
        - name: Loan-to-income ratio
          type: comparison
          entity: applicant
          left:
            relation: loan_amount
            value_type: int
          operator: "<="
          right:
            relation: salary
            multiplier: 5
            value_type: int
          message: "Loan amount must not exceed 5x monthly salary."
    """

    type: Literal["comparison"]
    entity: str = Field(min_length=1)
    left: ComparisonOperand
    operator: Literal["==", "!=", "<", ">", "<=", ">="]
    right: ComparisonOperand

    @model_validator(mode="after")
    def validate_comparison(self) -> "ComparisonRule":
        for operand, side in [(self.left, "left"), (self.right, "right")]:
            if operand.multiplier is not None and operand.multiplier == 0:
                raise ValueError(
                    f'ComparisonRule "{self.name}" {side}: multiplier cannot be 0'
                )
            if (operand.value_type == "int" and operand.multiplier is not None
                    and operand.multiplier != int(operand.multiplier)):
                raise ValueError(
                    f'ComparisonRule "{self.name}" {side}: '
                    f"int value_type requires integer multiplier, got {operand.multiplier}"
                )
        return self


class CardinalityRule(_RuleBase):
    """Count constraint: limit how many values an entity can have for a relation.

    Example YAML:
        - name: Max 2 primary diagnoses
          type: cardinality
          entity: patient
          relation: primary_diagnosis
          at_most: 2
          message: "A patient can have at most 2 primary diagnoses."

        - name: At least 1 emergency contact
          type: cardinality
          entity: employee
          relation: emergency_contact
          at_least: 1
          message: "Every employee should have at least 1 emergency contact."
    """

    type: Literal["cardinality"]
    entity: str = Field(min_length=1)
    relation: str = Field(min_length=1)
    at_most: Optional[int] = None
    at_least: Optional[int] = None

    @model_validator(mode="after")
    def validate_cardinality(self) -> "CardinalityRule":
        if self.at_most is None and self.at_least is None:
            raise ValueError(
                f'Cardinality rule "{self.name}" must specify at least one of '
                f"at_most or at_least."
            )
        if self.at_most is not None and self.at_most < 0:
            raise ValueError(
                f'Cardinality rule "{self.name}": at_most must be >= 0, got {self.at_most}'
            )
        if self.at_least is not None and self.at_least < 1:
            raise ValueError(
                f'Cardinality rule "{self.name}": at_least must be >= 1, got {self.at_least}'
            )
        if (self.at_most is not None and self.at_least is not None
                and self.at_least > self.at_most):
            raise ValueError(
                f'Cardinality rule "{self.name}": at_least ({self.at_least}) '
                f"cannot be greater than at_most ({self.at_most})"
            )
        return self


class CompositeCondition(BaseModel):
    """A single condition within all_of/any_of/none_of composition."""

    entity: str = Field(min_length=1)
    relation: str = Field(min_length=1)
    value: str = Field(min_length=1)
    operator: str = "="
    value_type: Literal["string", "int", "float", "date"] = "string"

    @model_validator(mode="after")
    def validate_operator_for_type(self) -> "CompositeCondition":
        valid = _NUMERIC_OPS if self.value_type != "string" else _STRING_OPS
        if self.operator not in valid:
            raise ValueError(
                f'Operator "{self.operator}" is not valid for value_type '
                f'"{self.value_type}". Valid: {valid}'
            )
        return self


class CompositionRule(_RuleBase):
    """Composite condition rule: AND/OR/NOT logic over multiple conditions.

    Example YAML:
        - name: Elderly diabetic checkup
          type: composition
          all_of:
            - entity: patient
              relation: age
              operator: ">"
              value: "60"
              value_type: int
            - entity: patient
              relation: condition
              value: diabetes
          then:
            require:
              relation: annual_checkup
              value: required
          message: "Elderly patients with diabetes must have annual checkups."
    """

    type: Literal["composition"]
    all_of: Optional[list[CompositeCondition]] = None
    any_of: Optional[list[CompositeCondition]] = None
    none_of: Optional[list[CompositeCondition]] = None
    then: ThenClause

    @model_validator(mode="after")
    def require_at_least_one_group(self) -> "CompositionRule":
        has_conditions = False
        for group in (self.all_of, self.any_of, self.none_of):
            if group and len(group) > 0:
                has_conditions = True
                break
        if not has_conditions:
            raise ValueError(
                f'Composition rule "{self.name}" must specify at least one '
                f"non-empty condition list in all_of, any_of, or none_of."
            )
        return self


# =====================================================================
# Discriminated Union
# =====================================================================

Rule = Annotated[
    Union[
        UniqueRule,
        ExclusionRule,
        DependencyRule,
        RangeRule,
        NegationRule,
        TemporalRule,
        ComparisonRule,
        CardinalityRule,
        CompositionRule,
    ],
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
    relations: list[RelationDef] = Field(default_factory=list)
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
