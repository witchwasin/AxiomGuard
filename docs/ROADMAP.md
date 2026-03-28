# Roadmap to v1.0.0

> AxiomGuard's path from Beta to Production-Grade.

---

## Current: v0.5.0 (Beta) — Self-Correction Loop

- [x] Z3 verification engine with SRO triples
- [x] Multi-claim extraction & entity resolution
- [x] KnowledgeBase with YAML rule format
- [x] Selective verification & numeric/date rules
- [x] Chroma & Qdrant vector DB integration
- [x] Self-correction loop with retry logic
- [x] Published on PyPI

---

## v0.6.0 — Negation & Temporal Logic

**Goal:** Handle real-world language complexity beyond simple "X is Y" facts.

| Feature | Description | Example |
|---------|-------------|---------|
| Negation handling | "The company is NOT in Chiang Mai" | Negated claims produce correct Z3 assertions |
| Temporal rules | "CEO was Somchai until 2025" | Time-bounded axioms with validity windows |
| Advanced entity normalization | "Bangkok" = "BKK" = "Krung Thep" | Configurable alias resolution beyond YAML |
| Confidence scoring | Per-claim extraction confidence | Filter low-confidence claims before Z3 |

---

## v0.7.0 — Advanced Rule Types

**Goal:** Cover the full range of enterprise domain constraints.

| Feature | Description | Example |
|---------|-------------|---------|
| Comparison rules | `>`, `<`, `>=`, `<=`, `!=` | "Loan amount must be <= 5x salary" |
| Cardinality constraints | "At most N" / "At least N" | "A patient can have at most 2 primary diagnoses" |
| Conditional chains | If A then B, if B then C | Multi-step dependency validation |
| Rule composition | Combine rules with AND/OR/NOT | Complex policy enforcement |

---

## v0.8.0 — Performance & Production Hardening

**Goal:** Make AxiomGuard fast enough for real-time production pipelines.

| Feature | Description | Target |
|---------|-------------|--------|
| Verification cache | Cache Z3 results for repeated claim patterns | 2x throughput |
| Parallel verification | Verify multiple claims concurrently | < 5ms per claim |
| Lazy rule loading | Load only relevant rules per query | Reduce memory for large rule sets |
| Structured logging | JSON logs for observability | Datadog/Grafana ready |
| Error recovery | Graceful degradation when Z3 or LLM fails | Never block the pipeline |

---

## v0.9.0 — Benchmarks & Validation

**Goal:** Prove AxiomGuard works on real-world hallucination problems.

| Feature | Description |
|---------|-------------|
| HaluEval benchmark | Test against HaluEval dataset (QA, dialogue, summarization) |
| TruthfulQA benchmark | Measure improvement on TruthfulQA |
| Domain-specific benchmarks | Medical (MIMIC), Legal (ContractNLI), Financial |
| Latency benchmarks | End-to-end pipeline timing across claim volumes |
| Cost analysis | Token cost comparison: with/without self-correction |
| Published results | Reproducible benchmark suite in `benchmarks/` |

---

## v1.0.0 — Production Release

**Goal:** Stable, documented, battle-tested, and trusted by the community.

### Stability
- [ ] Semantic versioning with backward-compatibility guarantees
- [ ] Deprecation warnings for any breaking changes
- [ ] Minimum 90% test coverage
- [ ] Python 3.9-3.13 CI matrix (all green)

### Documentation
- [ ] Full API reference (Sphinx or MkDocs)
- [ ] Integration guides (LangChain, LlamaIndex, Haystack)
- [ ] Domain cookbook: Healthcare, Legal, Finance, HR examples
- [ ] Video tutorial / walkthrough

### Ecosystem
- [ ] LangChain integration (`AxiomGuardChain`)
- [ ] LlamaIndex integration (`AxiomGuardPostprocessor`)
- [ ] REST API wrapper (FastAPI) for language-agnostic usage
- [ ] Docker image for self-hosted deployment

### Community
- [ ] GitHub Discussions enabled
- [ ] First 10 external contributors
- [ ] Conference talk / blog post about neuro-symbolic verification

---

## Beyond v1.0.0 — Future Vision

| Direction | Description |
|-----------|-------------|
| **Multi-language** | Thai, Japanese, Chinese NL-to-Logic translation |
| **Learning rules** | Auto-generate `.axiom.yml` from documents |
| **Distributed verification** | Verify across multiple knowledge bases |
| **Streaming support** | Verify LLM token streams in real-time |
| **Fine-tuned extractors** | Small models trained specifically for SRO extraction |

---

*This roadmap is a living document. Priorities may shift based on community feedback and real-world usage.*
