# AxiomGuard

**AxiomGuard is not smart. It is correct.**

Deterministic verification engine for LLM outputs.
Powered by Z3 Theorem Prover. Fully auditable. Zero false positives.
You write the rules. We enforce them with mathematical proof.

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

-   **Architecture Philosophy**

    Why we follow "Dumb but Unbreakable" — zero LLM in the error path.

    [:octicons-arrow-right-24: Philosophy](guides/architecture-philosophy.md)

-   **API Reference**

    Complete reference for all functions and classes.

    [:octicons-arrow-right-24: API Docs](api-reference.md)

</div>

---

## Two Ways to Create Rules (BYOR)

AxiomGuard is an enforcement engine. **You** write the rules — we enforce them.

=== "YAML (Recommended)"

    ```yaml
    rules:
      - name: hq_location
        type: unique
        entity: company
        relation: location
        value: Bangkok
        severity: error
        message: "HQ is Bangkok — not negotiable."
        #         ↑ This EXACT string is returned on violation.
    ```

=== "Programmatic (RuleBuilder)"

    ```python
    from axiomguard import RuleBuilder

    kb = (
        RuleBuilder(domain="company")
        .unique("hq", entity="company", relation="location",
                value="Bangkok", message="HQ is Bangkok.")
        .to_knowledge_base()
    )
    ```
