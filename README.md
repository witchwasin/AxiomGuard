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
  <strong>AxiomGuard is not smart. It is correct.</strong><br/><br/>
  Deterministic verification engine for LLM outputs.<br/>
  Powered by Z3 Theorem Prover. Zero false positives. Fully auditable.<br/>
  You write the rules. We enforce them with mathematical proof.
</p>

<p align="center">
  <a href="#the-pragmatic-enterprise-philosophy">Philosophy</a> &bull;
  <a href="#installation">Installation</a> &bull;
  <a href="#quickstart">Quickstart</a> &bull;
  <a href="#self-correction-loop">Self-Correction</a> &bull;
  <a href="#llm-backends">LLM Backends</a> &bull;
  <a href="#api-reference">API Reference</a> &bull;
  <a href="#architecture">Architecture</a> &bull;
  <a href="#contributing">Contributing</a>
</p>

---

## The Pragmatic Enterprise Philosophy

AxiomGuard follows the **"Dumb but Unbreakable"** doctrine. We deliberately reject intelligent verification in favor of mathematically provable, fully auditable, zero-surprise enforcement.

> *"A guardrail that sometimes works is worse than no guardrail at all — it creates false confidence."*

### 1. Deterministic Verification (Math > Vibes)

When Z3 says UNSAT, it's a **mathematical proof** — not an LLM's opinion. Same rules + same claims = same result, every time. No temperature, no randomness, no "it depends."

### 2. Bring Your Own Rules (BYOR)

AxiomGuard is an **enforcement engine**, not a rule generator. Domain experts (compliance officers, doctors, lawyers) write the rules in human-readable YAML. We enforce them. You own the liability — because you wrote the rules, not an AI.

### 3. Transparent Extraction (Auditability First)

The LLM extraction step is the weakest link — and we don't hide it. AxiomGuard always exposes the exact claims the LLM extracted **before** Z3 processes them. Auditors can immediately distinguish extraction errors from logic errors.

### 4. Zero-LLM Debugging (Hardcoded Error Mappings)

Every YAML rule has a `message` field written by a human. When Z3 returns UNSAT, AxiomGuard returns **exactly that string** — no LLM translation, no paraphrasing, no hallucinated explanations.

```yaml
- name: max_transfer_limit
  type: range
  entity: transaction
  relation: amount_thb
  max: 50000
  severity: error
  message: "Transaction exceeds 50,000 THB limit. Requires branch approval."
  #         ↑ This EXACT string is returned on violation. No LLM involved.
```

> Read the full [Architecture Philosophy](docs/architecture_philosophy.md) for the complete rationale and trust model.

---

## Why AxiomGuard?

Standard RAG pipelines retrieve context using **vector similarity** — but vectors encode *similarity*, not *truth*:

```
"The company is in Bangkok"     →  vector A
"The company is in Chiang Mai"  →  vector B

cosine_similarity(A, B) = 0.96  ← Almost identical — but logically contradictory!
```

| Feature | AxiomGuard | Prompt-based checks | Embedding filters |
|---------|:----------:|:-------------------:|:-----------------:|
| **Deterministic** (zero false positives) | Yes | No | No |
| **Auditable** (hardcoded error messages) | Yes | No | No |
| **Self-correcting** (auto-fix hallucinations) | Yes | No | No |
| **Zero token cost** for verification | Yes | No | Yes |
| **Latency** | ~10ms | 500ms+ | ~10ms |
| **Provider-agnostic** | Yes | Varies | N/A |

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

Basic verification (`verify()`) works **without any API key** using the built-in mock backend. For production use (complex sentence extraction, self-correction), set up an LLM backend:

```bash
# macOS / Linux
export ANTHROPIC_API_KEY="sk-ant-..."

# Windows (CMD)
set ANTHROPIC_API_KEY=sk-ant-...

# Windows (PowerShell)
$env:ANTHROPIC_API_KEY="sk-ant-..."
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

kb = KnowledgeBase()
kb.load("company.axiom.yml")
result = verify_with_kb("The CEO is John", kb)

print(result.is_hallucinating)   # True
print(result.violated_rules)     # [{'name': 'ceo_identity', 'message': 'CEO is Somchai.', ...}]
# ↑ The message is EXACTLY what the human wrote in YAML. No LLM translation.
```

### 3. Inspect Extracted Claims (Audit Trail)

```python
from axiomguard import extract_claims

claims = extract_claims("Transfer 800,000 THB to a crypto wallet")
for claim in claims:
    print(f"  {claim.subject}.{claim.relation} = {claim.object}")

# Auditor can verify: Did the LLM extract correctly?
# If it extracted "8000" instead of "800000" — that's an EXTRACTION error,
# not a Z3 error. Transparent. Traceable.
```

### 4. Self-Correction Loop (Auto-Fix Hallucinations)

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
print(result.response)  # The verified (or best-effort) response
print(result.attempts)  # How many tries it took
```

---

## Self-Correction Loop

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
│ Extract Claims│  SRO extraction (auditable)
└──────┬───────┘
       │
       ▼
┌──────────────┐
│ Z3 Verify    │  YAML rules → hardcoded message on failure
└──────┬───────┘
       │
  ┌────┴────┐
  │         │
 SAT      UNSAT
  │         │
  ▼         ▼
DONE   Return hardcoded error_msg
       + build correction prompt
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

---

## API Reference

### Core Verification

| Function | Description |
|----------|-------------|
| `verify(response, axioms)` | Verify against inline axiom strings |
| `verify_with_kb(response, kb)` | Verify against a KnowledgeBase |
| `verify_chunks(chunks, kb)` | Verify & annotate RAG chunks |
| `generate_with_guard(prompt, kb, llm_generate)` | Self-correcting generation loop |
| `extract_claims(text)` | Extract SRO triples (auditable) |

### Data Models

| Class | Description |
|-------|-------------|
| `Claim` | Subject-Relation-Object triple (Pydantic validated) |
| `VerificationResult` | `is_hallucinating`, `reason`, `violated_rules` (hardcoded messages) |
| `CorrectionResult` | `status`, `response`, `attempts`, `history` |
| `KnowledgeBase` | YAML rule loader, compiler & verifier |

---

## Architecture

```
axiomguard/
├── __init__.py              # Public API
├── core.py                  # Orchestration: extraction → resolution → Z3
├── z3_engine.py             # Z3 SMT solver: formal proofs
├── models.py                # Claim, VerificationResult, CorrectionResult
├── knowledge_base.py        # YAML rule compiler & verifier
├── parser.py                # .axiom.yml → Pydantic rule objects
├── correction.py            # Self-correction prompt builder
├── resolver.py              # Entity normalization (deterministic)
├── integration.py           # Vector DB integration (Chroma, Qdrant)
└── backends/
    ├── anthropic_llm.py     # Claude
    ├── openai_llm.py        # GPT-4o
    └── generic_http_llm.py  # Ollama / vLLM / any OpenAI-compatible
```

### Trust Model

```
TRUSTED (deterministic, auditable):
  ├── YAML rules (.axiom.yml)  ← written by human domain experts
  ├── Z3 Solver (math)         ← formal proof, zero false positives
  └── Error messages            ← hardcoded in YAML, no LLM involved

UNTRUSTED (must audit):
  └── LLM extraction            ← always exposed for human review
```

### Design Principles

1. **ML handles language, Math handles truth.** Neither modifies the other.
2. **Zero-LLM-Middleman.** Z3 returns hardcoded messages, not LLM explanations.
3. **BYOR.** We provide the engine. You provide (and own) the rules.
4. **Extraction transparency.** Every claim is visible before Z3 processes it.
5. **Zero false positives.** When Z3 returns UNSAT, the contradiction is *proven*.

---

## Roadmap

- [x] **v0.5.1** — Core engine, self-correction, PyPI, 71 tests
- [x] **v0.6.0** — Hardened enforcement: temporal reasoning (Z3 time-delta math), block-and-escalate mode, structured input path, negation rules, extraction bias audit, confidence scoring, claim classification. **233 tests.**
- [ ] **v0.7.0** — Tournament mode (multi-strategy rule derivation), advanced rules, Axiom Studio, LangChain/LlamaIndex
- [ ] **v0.8.0** — Performance: caching, parallel verification
- [ ] **v0.9.0** — Benchmarks against real-world hallucination + bias datasets
- [ ] **v1.0.0** — Production release

See the full **[Roadmap](docs/ROADMAP.md)** and **[Architecture Philosophy](docs/architecture_philosophy.md)**.

---

## Contributing

See **[CONTRIBUTING.md](CONTRIBUTING.md)** for the full guide. Quick start:

```bash
git clone https://github.com/witchwasin/AxiomGuard.git
cd AxiomGuard
pip install -e ".[all,dev]"
pytest tests/
```

---

## Changelog

See **[CHANGELOG.md](CHANGELOG.md)** for the full version history.

---

## License

MIT License. See [LICENSE](LICENSE).

---

<p align="center">
  <sub>Built by <a href="https://github.com/witchwasin">Witchwasin K.</a> — because AI should prove its answers, not guess them.</sub>
</p>
