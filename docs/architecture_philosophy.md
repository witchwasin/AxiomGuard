# Architecture Philosophy: Dumb but Unbreakable

> **AxiomGuard is not smart. It is correct.**
>
> We deliberately reject "intelligent" verification in favor of
> mathematically provable, fully auditable, zero-surprise enforcement.

---

## The Problem with "Smart" Guardrails

Most AI safety tools use LLMs to check LLMs. This creates a chain of trust
that breaks in production:

```
LLM generates response
    → LLM extracts claims (can hallucinate extraction)
    → LLM explains violations (can hallucinate explanations)
    → LLM generates corrections (can hallucinate fixes)

Every arrow is a point of failure.
```

**Real-world failures we've seen:**

| Failure Mode | What Happens | Impact |
|-------------|--------------|--------|
| Garbage In | LLM extracts "5,000" instead of "50,000" from prompt | Z3 validates wrong data — false SAT |
| Fake Citation | LLM invents rule names that don't exist in YAML | Auditor trusts non-existent rule |
| Hallucinated UNSAT | LLM "explains" why something failed using made-up logic | Developers debug phantom issues |
| Auto-Generated Rules | LLM reads PDF and outputs YAML with invented constraints | Liability nightmare — who signed off? |

---

## Our Answer: Zero-LLM-Middleman

AxiomGuard follows one principle: **The LLM touches language. Z3 touches truth. Nothing else touches either.**

### What the LLM Does (and ONLY this)

```
Natural language text → Structured SRO triples
"The patient takes Ibuprofen" → {subject: "patient", relation: "medication", object: "Ibuprofen"}
```

That's it. The LLM is a translator. It does not verify, explain, or generate rules.

### What Z3 Does (and ONLY this)

```
SRO triples + YAML rules → SAT or UNSAT
If UNSAT → return the hardcoded error_msg from the YAML rule
```

Z3 does not interpret, summarize, or rephrase. It returns exactly what the human
rule author wrote in the `message` field.

### What Humans Do (and ONLY humans)

```
Write YAML rules → Review extracted claims → Approve/reject
```

Humans are the authority. Not LLMs. Not Z3. AxiomGuard is the enforcement
mechanism between human intent (YAML rules) and AI output (LLM responses).

---

## The Three Pillars

### 1. Deterministic Error Mapping

Every rule has a hardcoded `message` field written by a domain expert:

```yaml
- name: max_transfer_limit
  type: range
  entity: transaction
  relation: amount_thb
  value_type: int
  max: 50000
  severity: error
  message: "Transaction exceeds 50,000 THB limit. Requires branch approval."
```

When Z3 returns UNSAT for this rule, AxiomGuard returns **exactly** this string.
No LLM translation. No paraphrasing. No hallucinated explanation.

**Why this matters:**
- Auditors see the exact message the compliance officer wrote
- No "telephone game" where meaning shifts through LLM layers
- Error messages can be legally reviewed and signed off
- Same input always produces same output — testable, reproducible

### 2. Bring Your Own Rules (BYOR)

AxiomGuard is an **enforcement engine**, not a rule generator.

```
WE DO:                           WE DON'T:
✓ Enforce YAML rules via Z3      ✗ Auto-generate rules from documents
✓ Validate rule syntax            ✗ Interpret legal/medical PDFs
✓ Provide rule authoring UI       ✗ Claim our rules are "correct"
✓ Return pass/fail verdicts       ✗ Provide legal/medical advice
```

**Why we killed auto-rule generation:**
- LLMs hallucinate constraints that don't exist in source documents
- "AI-generated compliance rules" is a liability sentence
- No one can sign off on rules they didn't write
- The value of rules comes from human domain expertise, not AI guessing

**What we provide instead:**
- Clean YAML schema with validation (Pydantic)
- Axiom Studio — a visual UI to help humans write correct YAML
- Inline examples for self-testing rules
- Clear error messages when rules are malformed

### 3. Extraction Transparency

The LLM extraction step is the weakest link. We make it fully visible:

```python
result = verify_with_kb("Transfer 50,000 THB to crypto wallet", kb)

# BEFORE Z3 processes anything, you can inspect:
result.extracted_claims
# [
#   Claim(subject="transaction", relation="amount_thb", object="50000"),
#   Claim(subject="transaction", relation="category", object="cryptocurrency"),
# ]

# The auditor can verify: Did the LLM extract correctly?
# If it extracted "5000" instead of "50000" — that's an EXTRACTION error,
# not a Z3 error. The math was correct; the input was wrong.
```

**Why this matters:**
- Separates "extraction error" from "logic error"
- Auditors can trace exactly where things went wrong
- No black box — every step is inspectable
- Enables human-in-the-loop review before enforcement

---

## Trust Model

```
┌─────────────────────────────────────────────────┐
│              TRUST BOUNDARY                      │
│                                                  │
│  ┌───────────┐     ┌────────────┐               │
│  │ Human     │────→│ YAML Rules │  100% trusted  │
│  │ Expert    │     │ (.axiom.yml)│  (human-authored)
│  └───────────┘     └─────┬──────┘               │
│                          │                       │
│                          ▼                       │
│                    ┌───────────┐                  │
│                    │ Z3 Solver │  100% trusted    │
│                    │ (math)    │  (formal proof)  │
│                    └─────┬─────┘                  │
│                          │                       │
├──────────────────────────┼───────────────────────┤
│  UNTRUSTED ZONE          │                       │
│                          │                       │
│  ┌───────────┐     ┌─────┴─────┐                │
│  │ LLM       │────→│ Extracted │  NOT trusted    │
│  │ (any)     │     │ Claims    │  (must audit)   │
│  └───────────┘     └───────────┘                │
│                                                  │
│  The LLM is a translator, not an authority.      │
│  Its output is ALWAYS subject to Z3 verification │
│  AND human audit.                                │
└─────────────────────────────────────────────────┘
```

---

## What This Means for Each Stakeholder

### For Enterprise Architects
- No LLM in the critical path of verification
- Deterministic: same rules + same claims = same result, every time
- Auditable: every step has a paper trail
- No vendor lock-in: Z3 is open source, YAML is portable

### For Compliance Officers
- You write the rules, you own the rules
- Error messages are exactly what you wrote — no AI paraphrasing
- Rules can be version-controlled, reviewed, and signed off
- No "AI told me this was compliant" liability

### For Developers
- Simple API: `verify(response, axioms)` → `True/False` + hardcoded reason
- No prompt engineering for the verification layer
- Predictable performance (~10ms, no LLM API calls for verification)
- Easy to test: rules are data, not code

### For Auditors
- Full extraction log: see exactly what the LLM extracted
- Clear separation: extraction error vs logic error vs rule error
- Hardcoded error messages traceable to specific YAML rules
- No hidden LLM calls in the verification pipeline

---

## FAQ

**Q: Why not use LLMs to generate rules? It's faster.**
A: Speed without accuracy is dangerous. An LLM that invents a rule about
"maximum 10 concurrent prescriptions" when the actual policy says 5 creates
a compliance gap that no one catches because "the AI wrote it."

**Q: Why not use LLMs to explain Z3 results? It's more user-friendly.**
A: Because LLMs hallucinate explanations. We've seen cases where the LLM
"explains" an UNSAT result by citing rules that don't exist. A hardcoded
`message` field is less eloquent but 100% accurate.

**Q: Doesn't this limit AxiomGuard's intelligence?**
A: Yes. Deliberately. AxiomGuard is not intelligent. It is correct.
Intelligence is the LLM's job. Correctness is ours.

**Q: What about the extraction step? That still uses an LLM.**
A: Correct. The LLM extraction is the one untrusted step. That's why we
enforce Extraction Transparency — every claim is exposed for audit before
Z3 processes it. We don't hide the weak link; we spotlight it.

---

*"A guardrail that sometimes works is worse than no guardrail at all —
it creates false confidence." — Enterprise Architect feedback, 2026-03-29*
