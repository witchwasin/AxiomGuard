# Architecture Vision: Hybrid Neuro-Symbolic RAG

> **Status:** Accepted
> **Date:** 2026-03-28
> **Context:** Community feedback on initial Neuro-Symbolic pipeline; pivot to Hybrid Retrieval Architecture

---

## 1. The Core Problem: Standard RAG Limitations

Retrieval-Augmented Generation (RAG) pipelines rely on vector similarity search to ground LLM outputs in factual data. The retrieval step typically encodes documents and queries into high-dimensional embeddings, then ranks candidates by a distance metric — most commonly **Cosine Similarity**.

This is fundamentally **probabilistic**. The vector space captures *semantic similarity* — how structurally and contextually similar two pieces of text are — not *logical consistency*.

### Why this fails in high-stakes domains

Consider two statements:

| Statement | Meaning |
|---|---|
| "The company headquarters is in **Bangkok**" | Ground truth |
| "The company headquarters is in **Chiang Mai**" | Factually wrong |

These two sentences share nearly identical structure, vocabulary, and topic. In embedding space, their cosine similarity is **very high** — they are close neighbors. A standard RAG retriever may surface either one with similar confidence, and the LLM has no mechanism to distinguish the correct one from the contradictory one.

This is not an edge case. It is a **structural blind spot** in vector similarity:

- **Legal:** "The contract terminates on March 31" vs. "The contract terminates on April 30" — near-identical embeddings, completely different legal obligations.
- **Medical:** "Patient is allergic to penicillin" vs. "Patient is not allergic to penicillin" — a single negation flips the meaning; the vectors barely move.
- **Financial:** "Revenue grew 12% YoY" vs. "Revenue grew 2% YoY" — numerically different, semantically indistinguishable to most embedding models.

In all these cases, the retriever treats contradictory facts as interchangeable because the **geometry of the vector space does not encode logical truth**. The result is hallucinations that look well-grounded — the most dangerous kind.

---

## 2. Our Solution: The Hybrid Approach (Best of Both Worlds)

AxiomGuard does not replace ML-based retrieval. It augments it with a deterministic logic layer, creating a **two-layer architecture** where each layer handles what it does best.

```
         Query (Natural Language)
                │
                ▼
  ┌───────────────────────────┐
  │   Layer 1: Probabilistic  │
  │   (ML / Semantic Layer)   │
  │                           │
  │   Embeddings, Vector DB,  │
  │   Semantic Similarity     │
  │                           │
  │   "Understand language"   │
  └─────────────┬─────────────┘
                │  Top-K candidates
                ▼
  ┌───────────────────────────┐
  │   Layer 2: Deterministic  │
  │   (Logic / Constraint)    │
  │                           │
  │   FOL, SMT Solver (Z3),  │
  │   Custom Distance Penalty │
  │                           │
  │   "Enforce truth"         │
  └─────────────┬─────────────┘
                │  Verified results
                ▼
          LLM Generation
```

### Layer 1: Probabilistic — The ML / Semantic Layer

**Role:** Process unstructured natural language data.

Pure deterministic or rule-based systems cannot handle the ambiguity, context-dependence, and variability of human language. A rule engine does not know that "HQ," "headquarters," and "main office" refer to the same concept — but an embedding model does.

ML acts as the **reader**:

- Encode documents and queries into dense vector representations
- Retrieve the top-K semantically relevant candidates from the vector store
- Handle synonymy, paraphrasing, and linguistic variation gracefully

This layer is intentionally left as a standard, well-understood RAG retriever. We do not modify it. We build on top of it.

### Layer 2: Deterministic — The Logic / Constraint Layer

**Role:** Apply formal mathematical constraints to reject logically invalid results.

After Layer 1 surfaces semantically relevant candidates, Layer 2 checks whether those candidates are **logically consistent** with a set of ground-truth axioms. It operates at the retrieval or verification stage as one of:

- **Custom Distance Penalty:** Modify the retrieval ranking by penalizing candidates that contradict known axioms. A result that is semantically close but logically inconsistent gets pushed down or filtered out entirely.
- **Post-Retrieval Filter:** After top-K retrieval, verify each candidate against axioms using an SMT solver (Z3). Discard any candidate where the solver returns UNSAT (proven contradiction).
- **Generation-Time Verifier:** After the LLM generates a response using retrieved context, verify the response against axioms before returning it to the user.

This layer is the **enforcer**. It does not understand language — it does not need to. It receives structured logical representations (produced by Layer 1's LLM translator) and applies the only question that matters: *does this contradict what we know to be true?*

### Why both layers are necessary

| Capability | Layer 1 (ML) | Layer 2 (Logic) |
|---|---|---|
| Understand natural language | Yes | No |
| Handle synonyms and paraphrasing | Yes | No |
| Detect logical contradictions | No | Yes |
| Provide mathematical proof of correctness | No | Yes |
| Scale to unstructured data | Yes | Limited |
| Guarantee zero false positives on contradictions | No | Yes |

Neither layer alone is sufficient. ML without logic produces plausible-sounding hallucinations. Logic without ML cannot parse human language. The hybrid architecture gives us both.

---

## 3. Critical Constraints & Community Feedback

The following rules are derived from community feedback and research literature. They exist to prevent architectural missteps that would undermine the system's effectiveness.

### Rule 1: Do NOT alter the base embedding training

> **Constraint:** The formal logic layer must NOT interfere with the embedding model's training objective or vector space geometry.

It is tempting to inject logical constraints directly into the embedding training process — for example, adding a loss term that pushes contradictory statements apart in vector space. **This is the wrong approach.**

**Why:**

- **Semantic Distortion.** Embedding models learn a general-purpose semantic manifold from large-scale pretraining. Imposing rigid mathematical structures during training warps this manifold, degrading performance on the very thing embeddings are good at: capturing semantic nuance and similarity.
- **Bias Introduction.** Logical constraints baked into embeddings create implicit biases. The model starts encoding "what should be true" rather than "what the text says," making it unreliable as a general-purpose language understanding layer.
- **Out-of-Distribution (OOD) Failure.** A constrained embedding space is optimized for the specific axioms it was trained with. When it encounters domains, topics, or phrasings outside that distribution, the distorted geometry produces unpredictable and unreliable results. The model loses its ability to generalize.

**Bottom line:** The embedding model is a tool for understanding language. Let it do that job without interference.

### Rule 2: Apply math at the Index / Retrieval / Verification level

> **Constraint:** All formal logic and mathematical constraints must be applied *after* encoding — at the indexing, retrieval, or post-retrieval verification stage.

The mathematical layer operates on the **output** of the semantic layer, not its internals:

- **Custom Distance Metric:** Augment cosine similarity with a logic-aware penalty term at query time. The base similarity score is computed normally; the penalty is applied separately.
- **Index-Time Annotation:** When documents are indexed, pre-compute their FOL representations and store them alongside the vectors. At retrieval time, use these annotations for fast logical filtering.
- **Post-Retrieval Verification:** After the vector store returns top-K results, run each through the SMT solver against the active axiom set. Filter or re-rank based on logical consistency.

This separation of concerns keeps the semantic distribution intact while adding a mathematically rigorous verification layer on top.

### Rule 3: ROI of ML — spend compute where it matters

> **Constraint:** ML compute should be allocated strictly for unstructured text understanding. Truth-checking is delegated to the deterministic engine.

ML is expensive — in compute, latency, and unpredictability. We use it only where deterministic methods genuinely cannot operate: parsing and understanding natural language.

| Task | Method | Rationale |
|---|---|---|
| Encode text to vectors | ML (embeddings) | Language understanding requires learned representations |
| Translate NL to FOL | ML (LLM) | Parsing unstructured text into structured logic requires language understanding |
| Check logical consistency | Deterministic (Z3) | SMT solving is exact, fast, and provably correct — no ML needed |
| Explain contradictions | Deterministic + template | Unsat core provides the proof; explanation can be templated |
| Re-rank retrieval results | Hybrid | Base score from ML, penalty from logic layer |

The deterministic engine (Z3) solves most real-world verification queries in **microseconds to milliseconds**. There is no reason to approximate with ML what can be computed exactly with mathematics.

---

## Summary

AxiomGuard is a **Hybrid Neuro-Symbolic RAG** system. It preserves the strengths of ML-based retrieval while closing the logical blind spot that causes hallucinations in high-stakes domains.

The architecture is defined by a clear separation:

1. **ML handles language.** Embeddings, semantic search, and NL-to-FOL translation.
2. **Math handles truth.** SMT solving, contradiction detection, and provable guarantees.
3. **The two layers communicate through structured logical representations** — FOL formulas that serve as the bridge between probabilistic understanding and deterministic verification.

This is our North Star. Every design decision should be evaluated against these principles.
