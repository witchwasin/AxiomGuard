# Changelog

All notable changes to AxiomGuard will be documented in this file.

This project follows [Semantic Versioning](https://semver.org/).

---

## [0.5.1] - 2026-03-28

### Added
- **AI-Generated Rules (Mode 2)** — `generate_rules()` sends natural language documents to an LLM and returns valid `.axiom.yml` rules automatically
- **Programmatic Rules (Mode 3)** — `RuleBuilder` fluent API for building rules from code, databases, or APIs at runtime
- `generate_rules_to_kb()` — document to KnowledgeBase in one call
- `generate_rules_to_file()` — document to `.axiom.yml` file
- MkDocs Material documentation site (12 pages) with GitHub Pages auto-deploy
- 4 new example scripts: `loan_approval_demo.py`, `medical_bot_guard.py`, `document_to_rules_demo.py`, `medical_rules.axiom.yml`
- `py.typed` marker (PEP 561) for mypy/pyright support
- GitHub Issue & PR templates

### Fixed
- 7 test collection errors caused by helper function named `test()` — renamed to `_check()`
- Author name on PyPI corrected to "Witchwasin K."

### Changed
- **Three ways to create rules:** Manual (YAML) / AI-Generated (LLM) / Programmatic (RuleBuilder)
- Test count: 47 → 71 (24 new tests for rule generator)

---

## [0.5.0] - 2026-03-28

### Added
- **Self-Correction Loop** — `generate_with_guard()` detects hallucinations and auto-fixes them via retry with Z3 proof feedback
- `CorrectionResult` and `CorrectionAttempt` data models for full correction history tracking
- Correction prompt builder with Z3 proof trace injection (`correction.py`)
- Three-layer fail-safe: `max_retries`, `timeout_seconds`, `max_tokens_budget`
- Streamlit pitch demo app (`demo_app.py`) — Thai personal loan approval showcase
- `setup.py` for backward-compatible PyPI distribution
- Published to PyPI: `pip install axiomguard`

### Changed
- Bumped version to 0.5.0 across `pyproject.toml`, `setup.py`, `__init__.py`
- README rewritten with comparison table, badges, and 3-tier quickstart
- `__init__.py` exports organized by category with module docstring

### Research
- `docs/research/v050_self_correction_strategy.md` — full design spec for correction loop

---

## [0.4.0] - 2026-03-28

### Added
- **Selective Verification** — smart filtering of claims by axiom-relation overlap (skip irrelevant claims)
- **Numeric & Date Rules** — `range` rule type with `min`/`max`/`value_type` support in YAML
- **Chroma Integration** — `axiomguard.integrations.chroma` wrapper for ChromaDB vector stores
- **Qdrant Integration** — `axiomguard.integrations.qdrant` wrapper for Qdrant vector stores
- `verify_chunks()` — verify and annotate RAG chunks in bulk
- `verification_stats()` — summary statistics for batch verification
- Scaling benchmarks for 10k+ chunk pipelines

### Research
- `docs/research/v040_scaling_strategy.md` — post-reranking placement, 50-200ms latency target

---

## [0.3.0] - 2026-03-28

### Added
- **KnowledgeBase** — load domain rules from `.axiom.yml` files
- **YAML Rule Format** — declarative rules readable by domain experts (lawyers, doctors, analysts)
- Rule types: `unique`, `exclusion`, `dependency`, `range`
- **Explainable Proof Traces** — human-readable contradiction explanations with rule metadata
- `verify_with_kb()` — verify against a KnowledgeBase instead of inline axioms
- `AxiomParser` and `RuleSet` for programmatic rule management
- `violated_rules` field on `VerificationResult` (name, type, severity, message)

### Research
- `docs/research/v030_axiom_library_format.md` — YAML format spec, prior art comparison (NeMo, OPA, Drools, SHACL)

---

## [0.2.0] - 2026-03-28

### Added
- **Multi-Claim Extraction** — single sentence yields multiple SRO triples
- **Entity Resolution** — fuzzy matching + canonical name normalization (`EntityResolver`)
- `extract_claims()` — extract structured claims from natural language
- `Claim` model with `negated` field for negation detection
- `ExtractionResult` model with Pydantic validation
- Deduplication via `Claim.as_key()` (order-independent)

### Research
- `docs/research/v020_extraction_logic.md` — atomic proposition rules, JSON schema

---

## [0.1.0] - 2026-03-28

### Added
- **Z3 Verification Engine** — formal contradiction proofs via SMT solver
- **SRO Triple Translation** — natural language to Subject-Relation-Object structured logic
- **Multi-Provider Backends** — Anthropic (Claude), OpenAI (GPT-4o), Generic HTTP (Ollama/vLLM), Mock
- `verify()` — core verification function
- `translate_to_logic()` — NL to SRO triple
- `set_llm_backend()` — swap LLM providers in one line
- Uniqueness axiom: `ForAll(s, o1, o2): Rel(r,s,o1) ^ Rel(r,s,o2) -> o1 = o2`
- Hybrid retrieval proof-of-concept
- MIT License

### Research
- `docs/research/00-architecture-vision.md` — Neuro-Symbolic pipeline design
- `docs/research/00-hybrid-architecture.md` — why vectors encode similarity, not truth

---

[0.5.0]: https://github.com/witchwasin/AxiomGuard/compare/v0.4.0...v0.5.0
[0.4.0]: https://github.com/witchwasin/AxiomGuard/compare/v0.3.0...v0.4.0
[0.3.0]: https://github.com/witchwasin/AxiomGuard/compare/v0.2.0...v0.3.0
[0.2.0]: https://github.com/witchwasin/AxiomGuard/compare/v0.1.0...v0.2.0
[0.1.0]: https://github.com/witchwasin/AxiomGuard/releases/tag/v0.1.0
