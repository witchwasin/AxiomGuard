# Why We Don't Auto-Generate Rules

!!! warning "Architectural Decision"
    AxiomGuard deliberately does NOT use LLMs to generate YAML rules from documents. This page explains why.

## The Problem with AI-Generated Rules

Using an LLM to read a policy document and output YAML rules sounds efficient. In practice, it creates:

1. **Fake citations** — LLMs invent constraints that don't exist in the source document
2. **Hallucinated thresholds** — "Maximum 10 items" when the policy says 5
3. **Liability gap** — No human signed off on the generated rules
4. **False confidence** — Teams trust rules they didn't write or review

## Our Approach: BYOR (Bring Your Own Rules)

AxiomGuard is an **enforcement engine**, not a rule generator.

| We DO | We DON'T |
|-------|----------|
| Enforce YAML rules via Z3 | Auto-generate rules from documents |
| Validate rule syntax | Interpret legal/medical PDFs |
| Provide visual rule editor (Axiom Studio, coming in v0.7.0) | Claim our rules are "correct" |
| Return pass/fail with hardcoded messages | Provide legal/medical advice |

## How to Write Rules

- [YAML Rules Format](yaml-rules.md) — learn all rule types
- [Programmatic Rules](programmatic-rules.md) — build rules from code with `RuleBuilder`
- **Axiom Studio** (v0.7.0) — visual UI to help humans write and test YAML

## Legacy Note

The `generate_rules()` function exists in the codebase from v0.5.x but is **deprecated** and will be removed in a future version. Do not use it for production workloads.
