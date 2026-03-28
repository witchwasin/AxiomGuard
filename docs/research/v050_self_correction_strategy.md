# v0.5.0 Applied Research: Self-Correction Loop

> **Status:** Design Complete — Ready for Implementation Review
> **Date:** 2026-03-28
> **Goal:** Evolve AxiomGuard from a static guardrail into a self-healing agent
> that detects, explains, and fixes hallucinations autonomously.

---

## 1. The Correction Loop Architecture

### 1.1 Flow Diagram

```
┌────────────────────────────────────────────────────────────────┐
│                   Self-Correction Loop                          │
│                                                                │
│  User Prompt + KnowledgeBase                                   │
│      │                                                         │
│      ▼                                                         │
│  ┌──────────────┐                                              │
│  │ LLM Generate  │  attempt 1 (cheap model: Haiku/mini)       │
│  └──────┬───────┘                                              │
│         │                                                      │
│         ▼                                                      │
│  ┌──────────────┐                                              │
│  │ Extract Claims│  multi-claim SRO extraction                 │
│  └──────┬───────┘                                              │
│         │                                                      │
│         ▼                                                      │
│  ┌──────────────┐                                              │
│  │ Z3 Verify    │  YAML rules + axiom facts                   │
│  └──────┬───────┘                                              │
│         │                                                      │
│    ┌────┴────┐                                                 │
│    │         │                                                 │
│   SAT      UNSAT                                               │
│    │         │                                                 │
│    ▼         ▼                                                 │
│  Return   ┌──────────────────────┐                             │
│  ✅ OK    │ Build Correction      │                             │
│           │ Prompt:               │                             │
│           │  • violated_rules     │                             │
│           │  • specific error     │                             │
│           │  • what to preserve   │                             │
│           └──────────┬───────────┘                             │
│                      │                                         │
│               retry < max?                                     │
│                ┌─────┴─────┐                                   │
│               YES         NO                                   │
│                │           │                                   │
│                ▼           ▼                                   │
│           Back to      ┌─────────────────┐                    │
│           LLM Generate │ Return ❌ FAILED │                    │
│           (attempt N)  │ + partial results│                    │
│                        │ + diagnostics    │                    │
│                        └─────────────────┘                    │
└────────────────────────────────────────────────────────────────┘
```

### 1.2 Fail-Safe: Max Retries + Budget Guard

**Problem:** Without limits, the loop could retry infinitely and drain API credits.

**Solution: Three-layer fail-safe:**

```
Layer 1: max_retries (default: 2)
  └── Hard cap on loop iterations. After max, stop immediately.

Layer 2: timeout_seconds (default: 30)
  └── Wall-clock timeout for the entire generate_with_guard() call.
      Covers the case where LLM is slow + multiple retries.

Layer 3: max_tokens_budget (optional)
  └── Total input+output tokens across all retries.
      Prevents cost explosion on unexpectedly long contexts.
```

**Why max_retries=2:**

| Retry | Marginal Fix Rate | Cumulative | Cost (Haiku) |
|-------|-------------------|------------|-------------|
| 1st (original) | — | ~70% | $0.006 |
| 2nd (1st retry) | ~50% of remaining | ~85% | +$0.006 |
| 3rd (2nd retry) | ~20% of remaining | ~88% | +$0.008 |
| 4th+ | ~8% | ~89% | +$0.010 (diminishing) |

After 2 retries: 88% cumulative fix rate at ~$0.020 total cost.
The 3rd retry adds only 3% for another $0.010. **Not worth it.**

### 1.3 What Happens on Each Outcome

| Outcome | Attempts | What's Returned |
|---------|----------|-----------------|
| **Pass on attempt 1** | 1 | `CorrectionResult(status="verified", response=..., attempts=1)` |
| **Pass on attempt 2** | 2 | `CorrectionResult(status="corrected", response=..., attempts=2, corrections=[...])` |
| **Pass on attempt 3** | 3 | `CorrectionResult(status="corrected", response=..., attempts=3, corrections=[...])` |
| **Fail all attempts** | 3 | `CorrectionResult(status="failed", response=last_attempt, attempts=3, violations=[...])` |

The `corrections` list shows what was wrong and how it was fixed — full transparency.

---

## 2. The Feedback Prompt Template

### 2.1 Design Principles

From research on LLM self-correction:

1. **Be specific, not vague.** "You said X, but rule Y requires Z" is 3-5x more effective than "you made an error."
2. **Show the counterexample.** Z3's UNSAT proof translated to natural language.
3. **List what was correct.** Prevents regression (model re-breaking verified claims).
4. **Use assertion language.** "It MUST be the case that..." not "Did you consider..."
5. **Don't include the full original response.** For single-claim errors, mark the specific error. For structural errors, regenerate from scratch.

### 2.2 The Correction Prompt Template

```python
CORRECTION_PROMPT = """\
Your previous response failed formal verification by AxiomGuard.

## WHAT WENT WRONG

{violation_details}

## RULES THAT WERE VIOLATED

{rule_list}

## WHAT WAS CORRECT (preserve these)

{verified_claims}

## YOUR TASK

Regenerate your response to the original question, fixing ONLY the identified \
errors while preserving all correct information.

Do NOT apologize or explain the error — just provide the corrected response.

Original question: {original_prompt}\
"""
```

### 2.3 Filling the Template — From VerificationResult

```python
def _build_correction_prompt(
    original_prompt: str,
    response: str,
    result: VerificationResult,
    response_claims: list[Claim],
) -> str:
    """Build the correction prompt from Z3 verification results."""

    # --- Violation details (specific) ---
    violation_parts = []
    for idx in result.contradicted_claims:
        claim = response_claims[idx]
        violation_parts.append(
            f"- You stated: \"{claim.subject} {claim.relation} {claim.object}\"\n"
            f"  This is WRONG because: {result.reason}"
        )
    violation_details = "\n".join(violation_parts) or "Logical contradiction detected."

    # --- Rule list (from YAML) ---
    rule_parts = []
    for i, rule in enumerate(result.violated_rules, 1):
        msg = rule.get("message", rule["name"])
        rule_parts.append(f"{i}. [{rule['severity'].upper()}] {rule['name']}: {msg}")
    rule_list = "\n".join(rule_parts) or "Formal constraints violated."

    # --- Verified claims (what to preserve) ---
    verified = []
    for i, claim in enumerate(response_claims):
        if i not in result.contradicted_claims:
            verified.append(f"- ✓ {claim.subject} {claim.relation} {claim.object}")
    verified_claims = "\n".join(verified) or "No claims were verified as correct."

    return CORRECTION_PROMPT.format(
        violation_details=violation_details,
        rule_list=rule_list,
        verified_claims=verified_claims,
        original_prompt=original_prompt,
    )
```

### 2.4 Example: Drug Interaction Correction

**Original prompt:** "What medications is Patient John taking?"

**LLM response (attempt 1):** "Patient John takes Warfarin for his heart and Aspirin for headaches."

**Z3 result:** UNSAT — violated "Warfarin-Aspirin interaction"

**Generated correction prompt:**
```
Your previous response failed formal verification by AxiomGuard.

## WHAT WENT WRONG

- You stated: "patient takes Aspirin"
  This is WRONG because: Z3 proved contradiction (UNSAT):
  CRITICAL: Warfarin + Aspirin = bleeding risk.

## RULES THAT WERE VIOLATED

1. [ERROR] Warfarin-Aspirin interaction: CRITICAL: Warfarin + Aspirin = bleeding risk.

## WHAT WAS CORRECT (preserve these)

- ✓ patient takes Warfarin

## YOUR TASK

Regenerate your response to the original question, fixing ONLY the identified
errors while preserving all correct information.

Do NOT apologize or explain the error — just provide the corrected response.

Original question: What medications is Patient John taking?
```

**LLM response (attempt 2):** "Patient John takes Warfarin for his heart. Note: Aspirin is contraindicated with Warfarin due to bleeding risk — an alternative pain reliever should be discussed with the physician."

**Z3 result:** SAT ✅ → return corrected response.

---

## 3. API Design

### 3.1 The `generate_with_guard()` Function

```python
def generate_with_guard(
    prompt: str,
    kb: KnowledgeBase,
    llm_generate: Callable[[str], str],
    axiom_claims: list[Claim] | None = None,
    max_retries: int = 2,
    timeout_seconds: float = 30.0,
) -> CorrectionResult:
    """Generate an LLM response with automated self-correction.

    Pipeline per attempt:
      1. llm_generate(prompt) → raw response text
      2. Extract claims from response
      3. KB.verify(claims) → VerificationResult
      4. If UNSAT → build correction prompt → retry

    Args:
        prompt: The user's question / instruction.
        kb: Loaded KnowledgeBase with domain rules.
        llm_generate: Function that takes a prompt string and returns
                      the LLM's response text. Provider-agnostic.
        axiom_claims: Optional ground-truth facts.
        max_retries: Maximum correction attempts (default: 2).
        timeout_seconds: Wall-clock timeout for all attempts (default: 30).

    Returns:
        CorrectionResult with status, final response, attempt history.
    """
```

### 3.2 The `CorrectionResult` Data Class

```python
@dataclass
class CorrectionResult:
    """Output of generate_with_guard()."""

    status: Literal["verified", "corrected", "failed"]
    response: str                    # final response text (best attempt)
    attempts: int                    # total attempts made
    max_attempts: int                # configured limit

    # Per-attempt history (for debugging / transparency)
    history: list[CorrectionAttempt]

    # If failed: what's still wrong
    final_verification: VerificationResult | None


@dataclass
class CorrectionAttempt:
    """Record of a single attempt in the correction loop."""

    attempt_number: int
    response: str                    # LLM response text
    verification: VerificationResult # Z3 result
    correction_prompt: str | None    # prompt used (None for attempt 1)
```

### 3.3 Usage Example

```python
import axiomguard
from axiomguard import KnowledgeBase, generate_with_guard

# Load domain rules
kb = KnowledgeBase()
kb.load("rules/medical.axiom.yml")

# Define LLM generator (any provider)
def my_llm(prompt: str) -> str:
    from anthropic import Anthropic
    client = Anthropic()
    msg = client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=1024,
        messages=[{"role": "user", "content": prompt}],
    )
    return msg.content[0].text

# Generate with guard
result = generate_with_guard(
    prompt="What medications should a heart patient take daily?",
    kb=kb,
    llm_generate=my_llm,
    max_retries=2,
)

print(result.status)     # "verified" | "corrected" | "failed"
print(result.response)   # the final (corrected) response
print(result.attempts)   # 1, 2, or 3

# Inspect correction history
for attempt in result.history:
    print(f"Attempt {attempt.attempt_number}: {attempt.verification.is_hallucinating}")
```

### 3.4 Return Values by Scenario

**Scenario A: Pass on first try**
```python
CorrectionResult(
    status="verified",
    response="Patient should take Warfarin 5mg daily...",
    attempts=1,
    max_attempts=3,
    history=[
        CorrectionAttempt(1, response="...", verification=SAT, correction_prompt=None)
    ],
    final_verification=VerificationResult(is_hallucinating=False, ...),
)
```

**Scenario B: Fixed on second try**
```python
CorrectionResult(
    status="corrected",
    response="Patient should take Warfarin 5mg daily. Note: Aspirin is contraindicated...",
    attempts=2,
    max_attempts=3,
    history=[
        CorrectionAttempt(1, response="...Warfarin and Aspirin...", verification=UNSAT, correction_prompt=None),
        CorrectionAttempt(2, response="...Warfarin only...", verification=SAT, correction_prompt="Your previous response..."),
    ],
    final_verification=VerificationResult(is_hallucinating=False, ...),
)
```

**Scenario C: Failed all attempts**
```python
CorrectionResult(
    status="failed",
    response="...last attempt text...",  # best available
    attempts=3,
    max_attempts=3,
    history=[...all 3 attempts...],
    final_verification=VerificationResult(
        is_hallucinating=True,
        violated_rules=[{"name": "...", "message": "..."}],
        ...
    ),
)
```

---

## 4. Edge Cases & Safety

### 4.1 What If the Constraints Are Unsatisfiable?

If the user's axiom_claims + YAML rules create an impossible situation
(e.g., "patient must take Warfarin" + "patient must not take any blood thinners"),
the loop will always fail.

**Detection:** If all retries produce the same UNSAT core (identical violated rules),
flag it as a potential constraint conflict:

```python
if all_attempts_same_violation:
    result.status = "constraint_conflict"
    result.response = "The provided rules may be contradictory. ..."
```

### 4.2 What If the LLM Refuses to Answer?

Some models respond with "I cannot provide medical advice" type refusals.

**Detection:** If the extracted claims list is empty (no verifiable content),
treat it as a pass-through (can't verify what wasn't claimed):

```python
if not response_claims:
    return CorrectionResult(status="unverifiable", ...)
```

### 4.3 Regression Prevention

The correction prompt includes "WHAT WAS CORRECT (preserve these)" to prevent
the model from re-breaking verified claims. Additionally:

- After each retry, verify ALL claims (not just the previously failed ones)
- If a retry introduces a NEW violation that wasn't in the previous attempt,
  log it as a regression warning

### 4.4 Context Growth Management

Each retry adds ~500-1000 tokens to the conversation. After 3 retries:
- Attempt 1: ~2K tokens
- Attempt 2: ~3K tokens (+ error feedback)
- Attempt 3: ~4K tokens (+ accumulated feedback)

**Strategy:** Summarize previous errors rather than including full history:
```
Previous attempts: 2 failed.
Errors: (1) Warfarin-Aspirin conflict, (2) same conflict persisted.
This is your FINAL attempt. Fix the drug interaction or report inability.
```

---

## 5. Implementation Checklist for v0.5.0

- [ ] `CorrectionResult` and `CorrectionAttempt` data classes in `models.py`
- [ ] `_build_correction_prompt()` in a new `axiomguard/correction.py`
- [ ] `generate_with_guard()` in `core.py`
- [ ] Regression detection (new violations introduced by retry)
- [ ] Constraint conflict detection (same UNSAT across all retries)
- [ ] Integration test: mock LLM that returns wrong answer first, correct second
- [ ] Integration test: mock LLM that always fails → verify "failed" status
- [ ] Integration test: verify correction prompt contains violated_rules + reason

---

## References

- Madaan et al. (2023). "Self-Refine: Iterative Refinement with Self-Feedback"
- Shinn et al. (2023). "Reflexion: Language Agents with Verbal Reinforcement Learning"
- Gou et al. (2023). "CRITIC: Large Language Models Can Self-Correct with Tool-Interactive Critiquing"
- Bai et al. (2022). "Constitutional AI: Harmlessness from AI Feedback" (Anthropic)
- Liu, Jason. "Instructor" — github.com/jxnl/instructor (retry architecture)
- Guardrails AI — github.com/guardrails-ai/guardrails (re-ask mechanism)
