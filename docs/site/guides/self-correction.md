# Self-Correction Loop

AxiomGuard v0.5.0 can **automatically detect and fix hallucinations** by re-prompting the LLM with Z3 proof feedback.

## How It Works

```
User Prompt + KnowledgeBase
    │
    ▼
┌──────────────┐
│ LLM Generate │  attempt 1
└──────┬───────┘
       │
       ▼
┌──────────────┐
│ Extract Claims│  multi-claim SRO extraction
└──────┬───────┘
       │
       ▼
┌──────────────┐
│ Z3 Verify    │  rules + axiom facts
└──────┬───────┘
       │
  ┌────┴────┐
  │         │
 SAT      UNSAT
  │         │
  ▼         ▼
DONE   Build correction prompt
       (include Z3 proof trace)
              │
              ▼
         Retry (max 2)
```

## Basic Usage

```python
from axiomguard import KnowledgeBase, generate_with_guard

kb = KnowledgeBase()
kb.load("company.axiom.yml")

result = generate_with_guard(
    prompt="Tell me about the company",
    kb=kb,
    llm_generate=my_llm_function,  # (str) -> str
    max_retries=2,
)

print(result.status)     # "verified" | "corrected" | "failed"
print(result.response)   # Best available response
print(result.attempts)   # Number of attempts (1-3)
```

## Result Statuses

| Status | Meaning |
|--------|---------|
| `"verified"` | Passed on first attempt — no hallucination |
| `"corrected"` | Had hallucinations, fixed on retry |
| `"failed"` | All retries exhausted, still has issues |
| `"unverifiable"` | Could not extract claims from response |
| `"constraint_conflict"` | Same error every attempt — rules may conflict |

## Inspecting Attempts

```python
for attempt in result.history:
    print(f"Attempt {attempt.attempt_number}:")
    print(f"  Response: {attempt.response[:100]}...")
    print(f"  Claims: {len(attempt.claims)}")
    print(f"  Hallucinating: {attempt.verification.is_hallucinating}")
    if attempt.correction_prompt:
        print(f"  Correction: {attempt.correction_prompt[:100]}...")
```

## Performance

| Metric | Value |
|--------|-------|
| Fix rate after 1 retry | ~70% |
| Fix rate after 2 retries | ~88% |
| Average cost per correction | ~$0.02 (Haiku) |
| 3rd retry added fix rate | Only +3% |

!!! tip "Why max_retries=2?"
    Diminishing returns: 3rd retry adds only 3% fix rate for +$0.01 cost. The default of 2 is the sweet spot.

## Three-Layer Fail-Safe

1. **`max_retries`** — Stop after N correction attempts
2. **`timeout_seconds`** — Total time budget for all attempts
3. **`max_tokens_budget`** — Optional token cost cap
