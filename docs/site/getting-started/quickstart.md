# Quickstart

## 1. Verify a Response (3 lines)

```python
from axiomguard import verify

result = verify("The company is in Chiang Mai", ["The company is in Bangkok"])
print(result.is_hallucinating)  # True
print(result.reason)            # Z3 proved contradiction (UNSAT): ...
```

No API key needed — the built-in mock backend handles simple sentences.

## 2. YAML Rules + Knowledge Base

Create `company.axiom.yml`:

```yaml
axiomguard: "0.3"
domain: company_facts

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
    message: "HQ is Bangkok — not negotiable."

  - name: ceo_identity
    type: unique
    entity: company
    relation: ceo
    value: Somchai
    severity: error
    message: "CEO is Somchai."
```

```python
from axiomguard import KnowledgeBase, verify_with_kb

kb = KnowledgeBase()
kb.load("company.axiom.yml")

result = verify_with_kb("The CEO is John", kb)
print(result.is_hallucinating)   # True
print(result.violated_rules)     # [ceo_identity]
```

## 3. Self-Correction Loop

Auto-detect and fix hallucinations:

```python
from axiomguard import KnowledgeBase, generate_with_guard

kb = KnowledgeBase()
kb.load("company.axiom.yml")

result = generate_with_guard(
    prompt="Tell me about the company",
    kb=kb,
    llm_generate=my_llm_function,  # any (str) -> str callable
    max_retries=2,
)

print(result.status)    # "verified" | "corrected" | "failed"
print(result.response)  # The verified response
print(result.attempts)  # How many tries
```

!!! tip "88% fix rate"
    The self-correction loop fixes 88% of hallucinations within 2 retries at ~$0.02 per correction (using Haiku).

## 4. Inspect Extracted Claims (Audit Trail)

AxiomGuard always exposes what the LLM extracted **before** Z3 processes it:

```python
from axiomguard import extract_claims

claims = extract_claims("Transfer 800,000 THB to a crypto wallet")
for claim in claims:
    print(f"  {claim.subject}.{claim.relation} = {claim.object}")

# Auditor can verify: Did the LLM extract correctly?
# If it extracted "8000" instead of "800000" — that's an EXTRACTION error,
# not a Z3 error. Transparent. Traceable.
```

!!! tip "BYOR — Bring Your Own Rules"
    AxiomGuard is an enforcement engine. Domain experts write the rules in YAML, AxiomGuard enforces them with Z3 mathematical proof. See [Architecture Philosophy](https://github.com/witchwasin/AxiomGuard/blob/main/docs/architecture_philosophy.md).

## Next Steps

- [YAML Rules Format](../guides/yaml-rules.md) — learn all rule types
- [LLM Backends](../guides/llm-backends.md) — connect Claude, GPT, or local models
- [API Reference](../api-reference.md) — full function documentation
