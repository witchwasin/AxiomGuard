<p align="center">
  <img src="https://img.shields.io/badge/status-Proof_of_Concept-yellow?style=for-the-badge" alt="poc" />
  <img src="https://img.shields.io/badge/AxiomGuard-v0.1.0-blue?style=for-the-badge" alt="version" />
  <img src="https://img.shields.io/badge/python-3.9+-green?style=for-the-badge&logo=python&logoColor=white" alt="python" />
  <img src="https://img.shields.io/badge/license-MIT-orange?style=for-the-badge" alt="license" />
  <img src="https://img.shields.io/badge/engine-Z3_SMT_Solver-red?style=for-the-badge" alt="z3" />
</p>

<h1 align="center">AxiomGuard</h1>

<p align="center">
  <strong>Eliminate AI Hallucinations Using Formal Mathematics</strong><br/>
  The first open-source <em>Hybrid Neuro-Symbolic</em> verification layer for RAG pipelines.<br/>
  Powered by the Z3 Theorem Prover. Provider-agnostic. Zero embedding modifications.
</p>

<p align="center">
  <a href="#quick-start">Quick Start</a> &bull;
  <a href="#how-it-works">How It Works</a> &bull;
  <a href="#llm-backends">LLM Backends</a> &bull;
  <a href="#api-reference">API Reference</a> &bull;
  <a href="#architecture">Architecture</a> &bull;
  <a href="#contributing">Contributing</a>
</p>

---

> **[Proof of Concept]** This project is an early-stage PoC exploring the idea of using formal mathematics (Z3 SMT Solver) to eliminate LLM hallucinations in RAG pipelines. The core equation works — but there's a long road ahead. If you find this idea interesting, have feedback, or want to help push it further: **fork it, hack on it, and open a PR.** All contributions and ideas are welcome. Let's build this together.
>
> Created by **Witchwasin K.** — [GitHub](https://github.com/witchwasin)

---

## The Problem

Standard RAG pipelines retrieve context using **vector similarity** (cosine distance). But vectors encode *semantic similarity*, not *logical truth*:

```
"The company is in Bangkok"     →  vector A
"The company is in Chiang Mai"  →  vector B

cosine_similarity(A, B) = 0.96  ← Almost identical!
```

These two sentences are **semantically almost identical** but **logically contradictory**. A standard RAG retriever treats them as interchangeable. The result: hallucinations that *look* well-grounded — the most dangerous kind.

This is not an edge case. It affects every high-stakes domain: legal contracts, medical records, financial reports, compliance policies.

## The Solution

AxiomGuard adds a **mathematically rigorous verification layer** on top of your existing RAG pipeline. No retraining. No embedding modifications. Just proof.

```python
from axiomguard import verify

result = verify(
    response="The company is in Chiang Mai",
    axioms=["The company is in Bangkok"],
)

print(result)
# VerificationResult(
#   is_hallucinating=True,
#   reason='Z3 proved contradiction (UNSAT): company.location cannot be
#           both "Bangkok" (axiom) and "Chiang Mai" (response)'
# )
```

When AxiomGuard says something is a hallucination, it's not a guess — it's a **mathematical proof**.

---

## How It Works

AxiomGuard is a **Hybrid Neuro-Symbolic** system. Two layers, each doing what it does best:

```
          Axioms (NL)           LLM Response (NL)
               │                       │
               ▼                       ▼
  ┌────────────────────┐  ┌────────────────────┐
  │  Layer 1: Neural   │  │  Layer 1: Neural   │
  │  (LLM Backend)     │  │  (LLM Backend)     │
  │                    │  │                    │
  │  NL → SRO Triple   │  │  NL → SRO Triple   │
  └─────────┬──────────┘  └──────────┬─────────┘
            │                        │
            │  {"subject": "company",│
            │   "relation":"location"│
            │   "object": "Bangkok"} │
            ▼                        ▼
       ┌─────────────────────────────────┐
       │     Layer 2: Symbolic           │
       │     (Z3 SMT Solver)             │
       │                                 │
       │  Uniqueness Axiom:              │
       │  ForAll(s, o1, o2):             │
       │    Rel(r,s,o1) ∧ Rel(r,s,o2)   │
       │    → o1 = o2                    │
       │                                 │
       │  Assert axioms + response       │
       │  check() → SAT / UNSAT         │
       └────────────────┬────────────────┘
                        │
                        ▼
                VerificationResult
```

| Layer | Role | Technology |
|---|---|---|
| **Neural (Layer 1)** | Translate natural language → structured logic | LLM (Claude, GPT, Llama, etc.) |
| **Symbolic (Layer 2)** | Prove contradictions mathematically | Z3 SMT Solver |

**Key principle:** ML handles language. Math handles truth. Neither is modified by the other.

---

## Quick Start

### Installation

```bash
pip install axiomguard
```

With a specific LLM backend:

```bash
pip install "axiomguard[anthropic]"   # Claude
pip install "axiomguard[openai]"      # GPT-4o
pip install "axiomguard[all]"         # Everything
```

### Basic Usage (Mock Backend)

Works immediately with zero API keys — uses a built-in rule-based translator:

```python
from axiomguard import verify

axioms = [
    "The company is in Bangkok",
    "The CEO is Somchai",
    "The product is AxiomGuard",
]

# Hallucinated response
result = verify("The company is in Chiang Mai", axioms)
print(result.is_hallucinating)  # True
print(result.reason)
# Z3 proved contradiction (UNSAT): company.location cannot be both
# "Bangkok" (axiom) and "Chiang Mai" (response)

# Truthful response
result = verify("The company is in Bangkok", axioms)
print(result.is_hallucinating)  # False
```

---

## LLM Backends

AxiomGuard is **provider-agnostic**. The verification engine (Z3) is always the same — only the NL-to-Logic translator changes. Swap backends in one line.

### Anthropic (Claude)

```bash
pip install "axiomguard[anthropic]"
export ANTHROPIC_API_KEY="sk-ant-..."
```

```python
import axiomguard
from axiomguard.backends.anthropic_llm import anthropic_translator

axiomguard.set_llm_backend(anthropic_translator)
result = axiomguard.verify("The company is in Chiang Mai", ["The company is in Bangkok"])
```

Use a specific model:

```python
from axiomguard.backends.anthropic_llm import create_anthropic_translator

backend = create_anthropic_translator(model="claude-sonnet-4-5-20250514")
axiomguard.set_llm_backend(backend)
```

### OpenAI (GPT-4o)

```bash
pip install "axiomguard[openai]"
export OPENAI_API_KEY="sk-..."
```

```python
import axiomguard
from axiomguard.backends.openai_llm import openai_translator

axiomguard.set_llm_backend(openai_translator)
```

Use a specific model:

```python
from axiomguard.backends.openai_llm import create_openai_translator

backend = create_openai_translator(model="gpt-4o")
axiomguard.set_llm_backend(backend)
```

### Local LLMs (Ollama / vLLM / LM Studio)

No extra dependencies. Works with any **OpenAI-compatible** HTTP endpoint:

```python
import axiomguard
from axiomguard.backends.generic_http_llm import create_http_translator

# Ollama (default: http://localhost:11434/v1)
axiomguard.set_llm_backend(create_http_translator(model="llama3.1"))

# vLLM / custom endpoint
axiomguard.set_llm_backend(create_http_translator(
    base_url="http://my-server:8080/v1",
    model="mistral-7b",
    api_key="optional-key",
))
```

### Custom Backend

Any function `(str) -> dict` works:

```python
import axiomguard

def my_backend(text: str) -> dict:
    # Your logic here — call any API, local model, or rule engine
    # Must return: {"subject": "...", "relation": "...", "object": "..."}
    return {"subject": "company", "relation": "location", "object": "Bangkok"}

axiomguard.set_llm_backend(my_backend)
```

---

## API Reference

### `verify(response, axioms) -> VerificationResult`

Verify an LLM response against ground-truth axioms.

```python
from axiomguard import verify

result = verify(
    response="The CEO is John",
    axioms=["The CEO is Somchai"],
)

result.is_hallucinating  # bool — True if Z3 proved a contradiction
result.reason            # str  — Human-readable explanation
```

### `translate_to_logic(text) -> dict`

Translate natural language to a Subject-Relation-Object triple.

```python
from axiomguard import translate_to_logic

triple = translate_to_logic("The company headquarters is in Bangkok")
# {"subject": "company", "relation": "location", "object": "Bangkok"}
```

### `set_llm_backend(backend)`

Replace the NL-to-Logic translator with any LLM backend.

```python
from axiomguard import set_llm_backend
```

---

## Architecture

```
axiomguard/
├── __init__.py              # Public API: verify, translate_to_logic, set_llm_backend
├── core.py                  # Orchestration: LLM translation → Z3 verification
├── z3_engine.py             # Z3 SMT solver: formal contradiction proofs
└── backends/
    ├── __init__.py          # Shared system prompt + response parser
    ├── anthropic_llm.py     # Anthropic Claude backend
    ├── openai_llm.py        # OpenAI GPT backend
    └── generic_http_llm.py  # Ollama / vLLM / any OpenAI-compatible endpoint
examples/
├── basic_usage.py           # Quick demo (mock backend)
└── real_llm_usage.py        # Demo with Anthropic API
tests/
├── test_z3_engine.py        # Z3 engine unit tests (7 cases)
└── poc_hybrid_retrieval.py  # Hybrid vector + logic ranking PoC
docs/research/
├── 00-architecture-vision.md    # Neuro-Symbolic pipeline design
└── 00-hybrid-architecture.md    # ADR: Hybrid Neuro-Symbolic RAG
```

### Design Principles

1. **ML handles language, Math handles truth.** The LLM translates text to structured logic. The Z3 solver proves contradictions. Neither modifies the other.
2. **Never alter the embedding space.** Logical constraints are applied at the verification/retrieval layer, not during encoding or training.
3. **Provider-agnostic.** The verification engine is the same regardless of which LLM translates the text. Swap providers in one line.
4. **Zero false positives on proven contradictions.** When Z3 returns UNSAT, the contradiction is mathematically proven — not estimated.

---

## Roadmap

- [x] **v0.1.0** — Z3 engine, SRO triples, multi-provider backends, hybrid retrieval PoC
- [ ] **v0.2.0** — Multi-claim extraction (one response = multiple SRO triples)
- [ ] **v0.3.0** — Self-correction loop (auto-fix hallucinated claims)
- [ ] **v0.4.0** — Vector DB integration (Pinecone, Weaviate, Chroma)
- [ ] **v1.0.0** — Production-grade pipeline with benchmarks

---

## Contributing

This is a PoC — there's plenty of room to explore. Here are some areas where contributions would be especially valuable:

- **Better NL-to-Logic translation** — improve entity normalization, handle multi-claim sentences
- **New relation types** — extend the Z3 engine to handle numeric comparisons, temporal logic, negation
- **Vector DB integrations** — plug AxiomGuard into Pinecone, Weaviate, Chroma, or Qdrant as a retrieval filter
- **Benchmarks** — test against real-world hallucination datasets and measure precision/recall
- **New LLM backends** — Google Gemini, Mistral, Cohere, or any provider you use

**How to contribute:**

```bash
git clone https://github.com/witchwasin/AxiomGuard.git
cd AxiomGuard
pip install -e ".[all]"
python tests/test_z3_engine.py      # make sure tests pass
# hack on it, then open a PR!
```

All ideas, feedback, and PRs are welcome — whether it's a bug fix, a new feature, or just a question in Issues.

---

## License

MIT License. See [LICENSE](LICENSE).

---

<p align="center">
  <sub>Built by <a href="https://github.com/witchwasin">Witchwasin K.</a> with Z3, formal mathematics, and the belief that AI should prove its answers.</sub>
</p>
