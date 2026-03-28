# AxiomGuard

**Mathematical Logic Guardrails for LLMs**

Deterministic hallucination detection & self-correction for RAG pipelines.
Powered by Z3 Theorem Prover. Provider-agnostic. Zero false positives.

---

## What is AxiomGuard?

AxiomGuard is a **Hybrid Neuro-Symbolic** verification layer that uses formal mathematics (Z3 SMT Solver) to **mathematically prove** whether LLM responses contain hallucinations.

```python
from axiomguard import verify

result = verify("The company is in Chiang Mai", ["The company is in Bangkok"])
print(result.is_hallucinating)  # True — Z3 proved it mathematically
```

!!! note "Not a guess — a proof"
    When AxiomGuard says it's a hallucination, it's backed by a formal mathematical proof from the Z3 theorem prover. Zero false positives on proven contradictions.

---

## Why AxiomGuard?

Standard RAG pipelines retrieve context using **vector similarity** — but vectors encode *similarity*, not *truth*:

```
"The company is in Bangkok"     → vector A
"The company is in Chiang Mai"  → vector B

cosine_similarity(A, B) = 0.96  ← Almost identical — but contradictory!
```

| Feature | AxiomGuard | Prompt-based | Embedding filters |
|---------|:----------:|:------------:|:-----------------:|
| **Deterministic** (zero false positives) | Yes | No | No |
| **Explainable** (proof trace) | Yes | No | No |
| **Self-correcting** | Yes | No | No |
| **Zero token cost** for verification | Yes | No | Yes |
| **Latency** | ~10ms | 500ms+ | ~10ms |

---

## Quick Links

<div class="grid cards" markdown>

-   **Getting Started**

    Install and verify your first response in 3 lines.

    [:octicons-arrow-right-24: Installation](getting-started/installation.md)

-   **YAML Rules**

    Write domain rules readable by non-programmers.

    [:octicons-arrow-right-24: YAML Format](guides/yaml-rules.md)

-   **AI-Generated Rules**

    Let an LLM convert your policy documents into rules.

    [:octicons-arrow-right-24: Auto-generate](guides/ai-generated-rules.md)

-   **API Reference**

    Complete reference for all functions and classes.

    [:octicons-arrow-right-24: API Docs](api-reference.md)

</div>

---

## Three Ways to Create Rules

=== "Manual (YAML)"

    ```yaml
    rules:
      - name: hq_location
        type: unique
        entity: company
        relation: location
        value: Bangkok
    ```

=== "AI-Generated"

    ```python
    from axiomguard import generate_rules

    yaml_str = generate_rules("Company HQ is Bangkok. CEO is Somchai.")
    ```

=== "Programmatic"

    ```python
    from axiomguard import RuleBuilder

    kb = (
        RuleBuilder(domain="company")
        .unique("hq", entity="company", relation="location", value="Bangkok")
        .to_knowledge_base()
    )
    ```
