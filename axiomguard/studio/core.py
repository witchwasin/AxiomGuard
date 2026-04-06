"""
Axiom Studio Core — Pure logic for Axiom Studio, testable without Streamlit.

Contains all business logic: YAML generation, validation, claim testing.
The Streamlit UI (axiom_studio.py) imports these functions.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

import yaml

from axiomguard import KnowledgeBase, Claim


@dataclass
class StudioState:
    """In-memory state for the studio session."""

    domain: str = "my_domain"
    rules: list = field(default_factory=list)


def add_rule_to_state(state: StudioState, rule: dict) -> None:
    """Add a rule dict to the state."""
    state.rules.append(rule)


def remove_rule_from_state(state: StudioState, index: int) -> None:
    """Remove a rule by index."""
    if 0 <= index < len(state.rules):
        state.rules.pop(index)


def build_yaml_output(domain: str, rules: list) -> str:
    """Build a valid .axiom.yml string from domain + rules.

    Args:
        domain: Domain name.
        rules: List of rule dicts.

    Returns:
        YAML string ready for download or KnowledgeBase.load_string().
    """
    if not rules:
        return f'axiomguard: "0.7"\ndomain: {domain}\nrules: []\n'

    # Clean None values from rules
    clean_rules = []
    for rule in rules:
        clean = {k: v for k, v in rule.items() if v is not None and v != ""}
        # Ensure values list has at least 2 items for exclusion
        if clean.get("type") == "exclusion" and len(clean.get("values", [])) < 2:
            continue
        clean_rules.append(clean)

    doc = {
        "axiomguard": "0.7",
        "domain": domain,
        "rules": clean_rules,
    }
    return yaml.dump(doc, default_flow_style=False, allow_unicode=True, sort_keys=False)


def _normalize_rules(rules: list) -> list:
    """Auto-fill missing fields so simplified Studio rules pass Pydantic validation.

    The Studio frontend generates a simpler YAML format than the full
    AxiomGuard schema (e.g. no ``name`` or ``relation`` on range rules).
    This function fills in sensible defaults before the YAML is loaded
    into ``KnowledgeBase``.
    """
    normalized = []
    for idx, rule in enumerate(rules):
        r = dict(rule)
        rtype = r.get("type", "")

        # Auto-generate name if missing
        if not r.get("name"):
            entity = r.get("entity", r.get("left", "rule"))
            if isinstance(entity, dict):
                entity = entity.get("relation", "rule")
            r["name"] = f"{entity}_{rtype}_{idx + 1}"

        # Auto-fill relation where required and missing — use entity name
        # to avoid cross-rule collision in Z3 (all rules sharing "value")
        entity = r.get("entity", "unknown")
        if rtype in ("range", "exclusion", "negation") and not r.get("relation"):
            r["relation"] = entity

        # Negation: convert "values" → "must_not_include" for Pydantic
        if rtype == "negation":
            if "values" in r and "must_not_include" not in r:
                r["must_not_include"] = r.pop("values")

        # Comparison: wrap string left/right into ComparisonOperand dicts
        if rtype == "comparison":
            if not r.get("entity"):
                left_val = r.get("left", "entity")
                r["entity"] = left_val if isinstance(left_val, str) else left_val.get("relation", "entity")
            if isinstance(r.get("left"), str):
                r["left"] = {"relation": r["left"], "value_type": "int"}
            if isinstance(r.get("right"), str):
                right_obj = {"relation": r["right"], "value_type": "int"}
                if "multiplier" in r:
                    right_obj["multiplier"] = r.pop("multiplier")
                r["right"] = right_obj

        normalized.append(r)
    return normalized


def validate_yaml_input(yaml_str: str) -> dict:
    """Validate a YAML string as an AxiomGuard ruleset.

    Args:
        yaml_str: Raw YAML content.

    Returns:
        Dict with "valid", "rules", "domain", "error".
    """
    try:
        data = yaml.safe_load(yaml_str)
        if not isinstance(data, dict):
            return {"valid": False, "rules": [], "domain": "", "error": "Not a valid YAML dict"}

        rules = data.get("rules", [])
        domain = data.get("domain", "unknown")

        # Normalize simplified Studio format to full schema
        rules = _normalize_rules(rules)
        data["rules"] = rules

        # Re-serialize and validate by loading into KnowledgeBase
        normalized_yaml = yaml.dump(data, default_flow_style=False, allow_unicode=True, sort_keys=False)
        kb = KnowledgeBase()
        kb.load_string(normalized_yaml)

        return {"valid": True, "rules": rules, "domain": domain, "error": None}
    except Exception as e:
        return {"valid": False, "rules": [], "domain": "", "error": str(e)}


def verify_claim_against_rules(
    yaml_str: str,
    subject: str,
    relation: str,
    value: str,
) -> dict:
    """Test a single claim against the current rules.

    Args:
        yaml_str: The YAML rules string.
        subject: Claim subject.
        relation: Claim relation.
        value: Claim object value.

    Returns:
        Dict with "is_hallucinating", "reason", "violated_rules".
    """
    try:
        # Normalize simplified Studio format before verification
        data = yaml.safe_load(yaml_str)
        if isinstance(data, dict) and "rules" in data:
            data["rules"] = _normalize_rules(data.get("rules", []))

            # Filter rules to only those matching the subject entity
            # This prevents cross-rule contamination where Z3 returns SAT
            # because the claim doesn't match unrelated rules
            filtered = [
                r for r in data["rules"]
                if r.get("entity", "") == subject
                or r.get("left", {}).get("relation", "") == subject
                or (isinstance(r.get("left"), str) and r["left"] == subject)
            ]
            if filtered:
                data["rules"] = filtered

            yaml_str = yaml.dump(data, default_flow_style=False, allow_unicode=True, sort_keys=False)

        kb = KnowledgeBase()
        kb.load_string(yaml_str)

        claims = [Claim(subject=subject, relation=relation, object=value)]
        result = kb.verify(response_claims=claims)

        # Z3 "unknown" (timeout) must NOT be treated as SAT
        reason = result.reason or ""
        if "unknown" in reason.lower() or "timeout" in reason.lower():
            return {
                "is_hallucinating": False,
                "reason": reason,
                "violated_rules": [],
                "error": True,
                "z3_unknown": True,
            }

        return {
            "is_hallucinating": result.is_hallucinating,
            "reason": result.reason,
            "violated_rules": result.violated_rules,
        }
    except Exception as e:
        return {
            "is_hallucinating": False,
            "reason": f"Verification error: {e}",
            "violated_rules": [],
            "error": True,
        }
