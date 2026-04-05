"""
Axiom Studio — Visual Rule Editor & Tester for AxiomGuard.

A Streamlit-based UI where domain experts can:
  1. Write YAML rules with live preview
  2. Add rules via a visual form
  3. Test rules against sample claims with live Z3 verification
  4. Download the generated .axiom.yml file

BYOR principle: Axiom Studio helps humans write correct YAML.
It does NOT auto-generate rules from documents.

Run:
    pip install "axiomguard[studio]"
    streamlit run axiom_studio.py
"""

from __future__ import annotations

import yaml

# Core logic is separated for testability without Streamlit
from axiomguard_studio_core import (
    StudioState,
    add_rule_to_state,
    build_yaml_output,
    remove_rule_from_state,
    verify_claim_against_rules,
    validate_yaml_input,
)

try:
    import streamlit as st

    _HAS_STREAMLIT = True
except ImportError:
    _HAS_STREAMLIT = False


def main():
    if not _HAS_STREAMLIT:
        print("Axiom Studio requires Streamlit: pip install 'axiomguard[studio]'")
        return

    st.set_page_config(page_title="Axiom Studio", layout="wide", page_icon="🛡️")
    st.title("Axiom Studio")
    st.caption("Visual Rule Editor & Tester for AxiomGuard — BYOR: You write the rules, we enforce them.")

    # Initialize state
    if "rules" not in st.session_state:
        st.session_state.rules = []
    if "domain" not in st.session_state:
        st.session_state.domain = "my_domain"

    # Layout: two columns
    left, right = st.columns([1, 1])

    # ---- LEFT: Rule Editor ----
    with left:
        st.subheader("Rule Editor")

        st.session_state.domain = st.text_input("Domain", value=st.session_state.domain)

        with st.expander("Add New Rule", expanded=True):
            rule_type = st.selectbox(
                "Type",
                ["unique", "exclusion", "range", "dependency", "negation",
                 "comparison", "cardinality", "composition"],
            )

            name = st.text_input("Rule Name", placeholder="e.g., max_loan_amount")
            entity = st.text_input("Entity", placeholder="e.g., applicant")
            relation = st.text_input("Relation", placeholder="e.g., loan_amount")
            message = st.text_input("Error Message", placeholder="Human-readable error")
            severity = st.selectbox("Severity", ["error", "warning", "info"])

            # Type-specific fields
            extra = {}
            if rule_type == "range":
                c1, c2 = st.columns(2)
                min_val = c1.text_input("Min", placeholder="optional")
                max_val = c2.text_input("Max", placeholder="optional")
                vtype = st.selectbox("Value Type", ["int", "float"])
                extra = {
                    "value_type": vtype,
                    "min": float(min_val) if min_val else None,
                    "max": float(max_val) if max_val else None,
                }
            elif rule_type == "exclusion":
                values = st.text_input("Excluded Values (comma-separated)")
                extra = {"values": [v.strip() for v in values.split(",") if v.strip()]}
            elif rule_type == "negation":
                forbidden = st.text_input("Must NOT Include (comma-separated)")
                extra = {"must_not_include": [v.strip() for v in forbidden.split(",") if v.strip()]}
            elif rule_type == "cardinality":
                c1, c2 = st.columns(2)
                at_most = c1.text_input("At Most", placeholder="optional")
                at_least = c2.text_input("At Least", placeholder="optional")
                extra = {
                    "at_most": int(at_most) if at_most else None,
                    "at_least": int(at_least) if at_least else None,
                }

            if st.button("Add Rule", type="primary"):
                if name and entity and relation:
                    rule = {
                        "name": name,
                        "type": rule_type,
                        "entity": entity,
                        "relation": relation,
                        "severity": severity,
                        "message": message,
                        **extra,
                    }
                    st.session_state.rules.append(rule)
                    st.success(f"Added: {name}")
                    st.rerun()
                else:
                    st.error("Name, Entity, and Relation are required.")

        # Show existing rules
        if st.session_state.rules:
            st.subheader(f"Rules ({len(st.session_state.rules)})")
            for i, rule in enumerate(st.session_state.rules):
                c1, c2 = st.columns([4, 1])
                c1.write(f"**{rule['name']}** ({rule['type']}) — {rule.get('message', '')}")
                if c2.button("Remove", key=f"rm_{i}"):
                    st.session_state.rules.pop(i)
                    st.rerun()

    # ---- RIGHT: YAML Preview + Test ----
    with right:
        st.subheader("YAML Preview")

        yaml_output = build_yaml_output(
            domain=st.session_state.domain,
            rules=st.session_state.rules,
        )
        st.code(yaml_output, language="yaml")

        st.download_button(
            label="Download .axiom.yml",
            data=yaml_output,
            file_name=f"{st.session_state.domain}.axiom.yml",
            mime="text/yaml",
        )

        # ---- Test Section ----
        st.subheader("Test Your Rules")

        if st.session_state.rules:
            test_subject = st.text_input("Subject", placeholder="e.g., applicant")
            test_relation = st.text_input("Test Relation", placeholder="e.g., loan_amount")
            test_value = st.text_input("Value", placeholder="e.g., 100000")

            if st.button("Verify Claim"):
                if test_subject and test_relation and test_value:
                    result = verify_claim_against_rules(
                        yaml_str=yaml_output,
                        subject=test_subject,
                        relation=test_relation,
                        value=test_value,
                    )
                    if result["is_hallucinating"]:
                        st.error(f"UNSAT — Violation detected: {result['reason']}")
                        for v in result.get("violated_rules", []):
                            st.warning(f"Rule: {v['name']} — {v['message']}")
                    else:
                        st.success("SAT — No hallucination detected")
                else:
                    st.warning("Fill in Subject, Relation, and Value.")
        else:
            st.info("Add rules to start testing.")

        # ---- Import YAML ----
        st.subheader("Import YAML")
        uploaded = st.file_uploader("Upload .axiom.yml", type=["yml", "yaml"])
        if uploaded:
            result = validate_yaml_input(uploaded.read().decode("utf-8"))
            if result["valid"]:
                st.session_state.rules = result["rules"]
                st.session_state.domain = result["domain"]
                st.success(f"Imported {len(result['rules'])} rules")
                st.rerun()
            else:
                st.error(f"Invalid YAML: {result['error']}")


if __name__ == "__main__":
    main()
