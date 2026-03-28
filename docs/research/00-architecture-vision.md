# AxiomGuard Architecture Vision

## Overview

AxiomGuard eliminates LLM hallucinations through **Neuro-Symbolic AI** — combining the flexibility of neural language models with the rigor of formal mathematical verification. Rather than relying on probabilistic confidence scores, we prove whether an LLM's output is logically consistent with a given set of ground-truth axioms.

The core insight: if we can translate both the axioms and the LLM response into formal logic, we can use an automated theorem prover to **mathematically prove** whether a contradiction exists. No heuristics, no guessing — just proof.

## End-to-End Pipeline

```
 Axioms (NL)       LLM Response (NL)
      │                    │
      ▼                    ▼
┌──────────┐       ┌──────────────┐
│ Phase 1  │       │   Phase 2    │
│ Axiom    │       │   Claim      │
│ Formal.  │       │   Extraction │
└────┬─────┘       └──────┬───────┘
     │  FOL formulas      │  FOL formulas
     ▼                    ▼
   ┌──────────────────────────┐
   │         Phase 3          │
   │  Automated Theorem       │
   │  Proving (Z3 / SMT)      │
   └────────────┬─────────────┘
                │  SAT / UNSAT
                ▼
   ┌──────────────────────────┐
   │         Phase 4          │
   │  Reasoning &             │
   │  Self-Correction         │
   └──────────────────────────┘
                │
                ▼
        VerificationResult
```

---

## Phase 1: Axiom Formalization

**Goal:** Translate natural language axioms into First-Order Logic (FOL) expressions that an SMT solver can consume.

**Input:** A list of natural language axioms, e.g.:
- "The company headquarters is in Bangkok"
- "All premium users have access to the dashboard"

**Output:** FOL formulas in SMT-LIB2 compatible syntax, e.g.:
```smt2
(assert (= (location company) Bangkok))
(assert (forall ((u User)) (=> (premium u) (has-access u dashboard))))
```

**Process:**
- Use an LLM to parse each axiom into a structured logical representation
- Map entities and predicates to a consistent symbol table (ontology)
- Validate that the generated FOL is syntactically correct SMT-LIB2

### Bottlenecks

- **Syntax precision:** The SMT solver (Z3) requires exact SMT-LIB2 syntax. A single misplaced parenthesis or undeclared sort causes a hard failure. LLMs frequently produce *almost correct* but syntactically invalid formulas — close enough to look right, broken enough to not parse.
- **Ontology consistency:** Each axiom must use the same symbol names for the same concepts. If one axiom refers to `(location company)` and another to `(headquarters firm)`, Z3 treats them as unrelated — the contradiction is invisible. Building and enforcing a shared ontology across axioms is non-trivial.
- **Quantifier ambiguity:** Natural language is full of implicit quantifiers ("users can access..." — all users? some users? authenticated users?). Choosing the wrong quantifier changes the logical meaning entirely.
- **Open-world vs. closed-world:** Natural language axioms often assume a closed world ("the office is in Bangkok" implies it is *only* in Bangkok), but FOL defaults to open-world semantics. We need explicit closed-world constraints or unique-name axioms to capture the intended meaning.

---

## Phase 2: Claim Extraction

**Goal:** Extract verifiable claims from the LLM response and translate each claim into FOL.

**Input:** Free-form LLM response text, e.g.:
- "Our company, based in Chiang Mai, offers premium users limited dashboard access."

**Output:** A set of FOL assertions representing the claims:
```smt2
(assert (= (location company) ChiangMai))
(assert (forall ((u User)) (=> (premium u) (limited-access u dashboard))))
```

**Process:**
- Decompose the response into atomic claims (one fact per statement)
- Translate each claim into FOL using the **same ontology** established in Phase 1
- Tag each claim with its source span in the original text (for Phase 4 explainability)

### Bottlenecks

- **Claim decomposition:** A single sentence can contain multiple interleaved claims. Extracting them cleanly without losing context or introducing phantom claims is difficult.
- **Ontology alignment:** The response uses different vocabulary than the axioms. "Based in" must map to the same `location` predicate as "headquarters is in". This is effectively an entity resolution and predicate alignment problem.
- **Implicit claims:** Responses contain implicit information ("limited dashboard access" implies access exists but is restricted — how do we formalize "limited"?). Deciding what to formalize and what to ignore is a judgment call that affects both recall and precision.
- **Same LLM, same weaknesses:** If we use an LLM to translate claims to FOL, that LLM can itself hallucinate the translation. We need validation layers or constrained generation to ensure the FOL output actually represents what the response said.

---

## Phase 3: Automated Theorem Proving

**Goal:** Use an SMT solver to determine whether the claims (Phase 2) are logically consistent with the axioms (Phase 1).

**Input:** Combined FOL assertions from Phase 1 and Phase 2.

**Output:** One of:
- **UNSAT** — the combined assertions are contradictory (hallucination detected)
- **SAT** — no contradiction found (claims are consistent with axioms)
- **UNKNOWN** — the solver could not determine satisfiability within resource limits

**Process:**
- Merge all axiom formulas and claim formulas into a single SMT-LIB2 script
- Feed the script to Z3 (or another SMT solver)
- If UNSAT, extract the **unsatisfiable core** — the minimal subset of assertions that cause the contradiction

### Key considerations

- **Soundness guarantee:** If Z3 returns UNSAT, there is a genuine logical contradiction. This is the mathematical backbone of AxiomGuard — no false positives from the solver itself.
- **Completeness gap:** SAT does not mean the response is *true* — it means the response does not contradict the axioms. Claims about topics not covered by axioms will pass through unchecked.
- **Performance:** Most real-world verification queries are in decidable fragments (quantifier-free or EPR) and solve in milliseconds. Pathological quantifier nesting can cause timeouts.
- **UNKNOWN handling:** When the solver times out, we must decide whether to flag the response as uncertain or fall back to a softer verification method.

---

## Phase 4: Reasoning & Self-Correction

**Goal:** Translate the mathematical proof of contradiction back into human-readable language, and optionally guide the LLM to self-correct.

**Input:**
- The solver result (SAT/UNSAT)
- The unsatisfiable core (if UNSAT)
- The source span mapping from Phase 2

**Output:**
- A `VerificationResult` with a human-readable explanation
- Optionally, a corrected response or correction prompt for the LLM

**Process:**
- Map the unsatisfiable core back to the original axioms and response claims
- Generate a natural language explanation: "The response claims X, which contradicts axiom Y"
- For self-correction: construct a targeted prompt that presents the specific contradiction and asks the LLM to revise only the hallucinated portion

### Key considerations

- **Explainability:** The unsat core gives us a precise, minimal set of contradicting statements — far more useful than "this response might be wrong." We can point to exactly which claim contradicts which axiom.
- **Surgical correction:** Rather than regenerating the entire response, we can ask the LLM to fix only the contradicted claims while preserving correct content.
- **Feedback loop:** The corrected response can be re-verified (back to Phase 2), creating an iterative refinement loop that converges on a consistent output.

---

## Summary of Critical Research Challenges

| Challenge | Phase | Severity | Notes |
|---|---|---|---|
| LLM → exact SMT-LIB2 syntax | 1 & 2 | **High** | Core bottleneck. Constrained decoding or grammar-guided generation may help |
| Ontology alignment across axioms and claims | 1 & 2 | **High** | Requires a shared symbol table; entity resolution problem |
| Closed-world vs. open-world semantics | 1 | Medium | Needs explicit closure axioms |
| Implicit claim extraction | 2 | Medium | Precision-recall tradeoff in what gets formalized |
| Solver timeout on complex quantified formulas | 3 | Low | Rare in practice; can bound quantifier depth |
| LLM hallucinating the FOL translation itself | 1 & 2 | **High** | Meta-problem: the translator can hallucinate too |

---

## Next Steps

- **PoC (current):** Keyword-based contradiction detection in `axiomguard/core.py`
- **v0.1:** Integrate Z3 solver; hand-written FOL translations to validate the Phase 3 pipeline
- **v0.2:** LLM-based Phase 1 & 2 with constrained output parsing
- **v0.3:** Full pipeline with self-correction loop and explainability
