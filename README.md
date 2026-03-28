<p align="center">
  <a href="https://pypi.org/project/axiomguard/"><img src="https://img.shields.io/pypi/v/axiomguard?style=for-the-badge&color=blue" alt="PyPI Version" /></a>
  <a href="https://github.com/witchwasin/AxiomGuard/actions"><img src="https://img.shields.io/github/actions/workflow/status/witchwasin/AxiomGuard/ci.yml?style=for-the-badge&label=CI" alt="CI" /></a>
  <img src="https://img.shields.io/badge/tests-71%20passed-brightgreen?style=for-the-badge" alt="Tests" />
  <img src="https://img.shields.io/badge/python-3.9+-green?style=for-the-badge&logo=python&logoColor=white" alt="Python" />
  <a href="LICENSE"><img src="https://img.shields.io/badge/license-MIT-orange?style=for-the-badge" alt="License" /></a>
  <img src="https://img.shields.io/badge/engine-Z3_SMT_Solver-red?style=for-the-badge" alt="Z3" />
</p>

<h1 align="center">AxiomGuard</h1>

<p align="center">
  <strong>Mathematical Logic Guardrails for LLMs</strong><br/>
  Deterministic hallucination detection & self-correction for RAG pipelines.<br/>
  Powered by Z3 Theorem Prover. Provider-agnostic. Zero false positives.
</p>

<p align="center">
  <a href="#why-axiomguard">Why AxiomGuard?</a> &bull;
  <a href="#installation">Installation</a> &bull;
  <a href="#quickstart">Quickstart</a> &bull;
  <a href="#self-correction-loop">Self-Correction</a> &bull;
  <a href="#llm-backends">LLM Backends</a> &bull;
  <a href="#api-reference">API Reference</a> &bull;
  <a href="#architecture">Architecture</a> &bull;
  <a href="#contributing">Contributing</a>
</p>

---

## Why AxiomGuard?

Standard RAG pipelines retrieve context using **vector similarity** — but vectors encode *similarity*, not *truth*:

```
"The company is in Bangkok"     →  vector A
"The company is in Chiang Mai"  →  vector B

cosine_similarity(A, B) = 0.96  ← Almost identical — but logically contradictory!
```

AxiomGuard adds a **mathematically rigorous verification layer** that catches what vectors miss.

| Feature | AxiomGuard | Prompt-based checks | Embedding filters |
|---------|:----------:|:-------------------:|:-----------------:|
| **Deterministic** (zero false positives) | Yes | No | No |
| **Explainable** (proof trace, not vibes) | Yes | No | No |
| **Self-correcting** (auto-fix hallucinations) | Yes | No | No |
| **Zero token cost** for verification | Yes | No | Yes |
| **Latency** | ~10ms | 500ms+ | ~10ms |
| **Provider-agnostic** | Yes | Varies | N/A |

**When AxiomGuard says it's a hallucination, it's a mathematical proof — not a guess.**

---

## Installation

```bash
pip install axiomguard
```

With LLM backends:

```bash
pip install "axiomguard[anthropic]"   # Claude
pip install "axiomguard[openai]"      # GPT-4o
pip install "axiomguard[all]"         # Everything + vector DBs
```

### API Key Setup (for full features)

Basic verification (`verify()`) works **without any API key** using the built-in mock backend. For production use (complex sentences, AI-generated rules, self-correction), set up an LLM backend:

```bash
# Option A: Anthropic (Claude) — recommended
export ANTHROPIC_API_KEY="sk-ant-..."

# Option B: OpenAI (GPT-4o)
export OPENAI_API_KEY="sk-..."

# Option C: Local LLM (Ollama) — no API key needed
# Just run: ollama serve
```

> Each user provides their own API key. No keys are bundled with the package.

---

## Quickstart

### 1. Verify a Response (3 lines)

```python
from axiomguard import verify

result = verify("The company is in Chiang Mai", ["The company is in Bangkok"])
print(result.is_hallucinating)  # True
print(result.reason)            # Z3 proved contradiction (UNSAT): ...
```

### 2. YAML Rules + Knowledge Base

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

kb = KnowledgeBase("company.axiom.yml")
result = verify_with_kb("The CEO is John and the company is in Chiang Mai", kb)
print(result.is_hallucinating)   # True
print(result.violated_rules)     # [hq_location, ceo_identity]
```

### 3. Self-Correction Loop (Auto-Fix Hallucinations)

```python
from axiomguard import KnowledgeBase, generate_with_guard

kb = KnowledgeBase("company.axiom.yml")

result = generate_with_guard(
    prompt="Tell me about the company",
    kb=kb,
    llm_generate=my_llm_function,  # any (str) -> str callable
    max_retries=2,
)

print(result.status)    # "verified" | "corrected" | "failed"
print(result.response)  # The verified (or best-effort) response
print(result.attempts)  # How many tries it took
```

> Detects hallucination → builds correction prompt with Z3 proof → regenerates → re-verifies. 88% cumulative fix rate after 2 retries at ~$0.02/correction.

---

## Self-Correction Loop

AxiomGuard v0.5.0 evolves from a static guardrail into a **self-healing agent**:

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
│ Z3 Verify    │  YAML rules + axiom facts
└──────┬───────┘
       │
  ┌────┴────┐
  │         │
 SAT      UNSAT
  │         │
  ▼         ▼
DONE   Build Correction Prompt
       (include Z3 proof trace)
              │
              ▼
         Retry (max 2)
```

**Three-layer fail-safe:** `max_retries` + `timeout_seconds` + optional `max_tokens_budget`.

---

## LLM Backends

AxiomGuard is **provider-agnostic**. The Z3 engine is always the same — only the NL-to-Logic translator changes.

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

### Local LLMs (Ollama / vLLM) — No API Key

```python
from axiomguard.backends.generic_http_llm import create_http_translator

axiomguard.set_llm_backend(create_http_translator(model="llama3.1"))
```

### Custom Backend

```python
def my_backend(text: str) -> dict:
    return {"subject": "company", "relation": "location", "object": "Bangkok"}

axiomguard.set_llm_backend(my_backend)
```

---

## API Reference

### Core Verification

| Function | Description |
|----------|-------------|
| `verify(response, axioms)` | Verify against inline axiom strings |
| `verify_with_kb(response, kb)` | Verify against a KnowledgeBase |
| `verify_chunks(chunks, kb)` | Verify & annotate RAG chunks |
| `generate_with_guard(prompt, kb, llm_generate)` | Self-correcting generation loop |
| `extract_claims(text)` | Extract SRO triples from text |
| `translate_to_logic(text)` | Single NL → SRO triple |

### Configuration

| Function | Description |
|----------|-------------|
| `set_llm_backend(backend)` | Swap NL-to-Logic provider |
| `set_entity_resolver(resolver)` | Custom entity normalization |
| `set_knowledge_base(kb)` | Set default KnowledgeBase |
| `load_rules(path)` | Load `.axiom.yml` rules |

### Data Models

| Class | Description |
|-------|-------------|
| `Claim` | Subject-Relation-Object triple (Pydantic validated) |
| `VerificationResult` | Z3 proof output: `is_hallucinating`, `reason`, `violated_rules` |
| `CorrectionResult` | Self-correction output: `status`, `response`, `attempts`, `history` |
| `KnowledgeBase` | YAML rule loader & manager |

---

## Architecture

```
axiomguard/
├── __init__.py              # Public API (clean re-exports)
├── core.py                  # Orchestration: extraction → resolution → Z3
├── z3_engine.py             # Z3 SMT solver: formal contradiction proofs
├── models.py                # Claim, VerificationResult, CorrectionResult
├── knowledge_base.py        # YAML rule loading & KnowledgeBase
├── parser.py                # .axiom.yml → rule objects
├── correction.py            # Self-correction prompt builder
├── resolver.py              # Entity normalization (fuzzy matching)
├── integration.py           # Vector DB integration (Chroma, Qdrant)
└── backends/
    ├── anthropic_llm.py     # Claude
    ├── openai_llm.py        # GPT-4o
    └── generic_http_llm.py  # Ollama / vLLM / any OpenAI-compatible
```

### Design Principles

1. **ML handles language, Math handles truth.** Neither modifies the other.
2. **Never alter the embedding space.** Verification is a separate layer.
3. **Provider-agnostic.** Swap LLM backends in one line. Z3 is always the judge.
4. **Zero false positives.** When Z3 returns UNSAT, the contradiction is *proven*.

---

## Roadmap

- [x] **v0.1.0** — Z3 engine, SRO triples, multi-provider backends
- [x] **v0.2.0** — Multi-claim extraction, entity resolution, fuzzy matching
- [x] **v0.3.0** — KnowledgeBase, explainable proof traces, YAML rules
- [x] **v0.4.0** — Selective verification, numeric/date rules, vector DB integration
- [x] **v0.5.0** — Self-correction loop, auto-fix hallucinations
- [ ] **v0.6.0** — Negation handling, temporal logic
- [ ] **v0.7.0** — Advanced rule types (comparisons, cardinality)
- [ ] **v0.8.0** — Performance optimization, caching, parallel verification
- [ ] **v0.9.0** — Benchmarking against real-world hallucination datasets
- [ ] **v1.0.0** — Production-grade release with LangChain/LlamaIndex integrations

See the full **[Roadmap to v1.0.0](docs/ROADMAP.md)** for details.

---

## Contributing

See **[CONTRIBUTING.md](CONTRIBUTING.md)** for the full guide. Quick start:

```bash
git clone https://github.com/witchwasin/AxiomGuard.git
cd AxiomGuard
pip install -e ".[all,dev]"
pytest tests/
```

All ideas, feedback, and PRs are welcome — see [where to contribute](CONTRIBUTING.md#where-to-contribute).

---

## Changelog

See **[CHANGELOG.md](CHANGELOG.md)** for the full version history.

---

## License

MIT License. See [LICENSE](LICENSE).

---

<p align="center">
  <sub>Built by <a href="https://github.com/witchwasin">Witchwasin K.</a> — proving that AI should prove its answers.</sub>
</p>
