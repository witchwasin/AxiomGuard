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

        # Validate by loading into KnowledgeBase
        kb = KnowledgeBase()
        kb.load_string(yaml_str)

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
        kb = KnowledgeBase()
        kb.load_string(yaml_str)

        claims = [Claim(subject=subject, relation=relation, object=value)]
        result = kb.verify(response_claims=claims)

        return {
            "is_hallucinating": result.is_hallucinating,
            "reason": result.reason,
            "violated_rules": result.violated_rules,
        }
    except Exception as e:
        return {
            "is_hallucinating": False,
            "reason": f"Error: {e}",
            "violated_rules": [],
        }
