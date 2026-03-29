# Changelog

All notable changes to AxiomGuard will be documented in this file.

This project follows [Semantic Versioning](https://semver.org/).

---

## [0.6.2] - 2026-03-30

### Fixed
- Bias audit false positives: word boundary matching prevents "man" from matching "permanently"

### Added
- Mars Rover edge safety demo (`examples/rover_edge_system.py` + `rover_safety_policy.axiom.yml`)

---

## [0.6.1] - 2026-03-30

### Fixed
- PyPI package now includes updated README with v0.6.0 roadmap checked off

---

## [0.6.0] - 2026-03-30

### Added
- **Temporal Reasoning** — `type: temporal` rules with Z3-powered time delta math. Supports event vs `system_time` (e.g., "review must be within 4h"), event vs event (e.g., "stay must be at least 1h"), and both min/max bounds. Human-readable delta format: `30s`, `5m`, `4h`, `7d`, `2w`. No LLM estimates passage of time — Z3 handles all calculations mathematically. (44 tests)
- **Block-and-Escalate Mode** — `generate_with_guard(mode="block"|"escalate")` halts immediately on Z3 UNSAT instead of retrying. `mode="escalate"` additionally calls an `on_escalate` callback for routing to human review queues. Default `mode="correct"` preserves existing retry behavior (backward compatible).
- **Structured Input Path** — `verify_structured()` accepts `Claim` objects or plain dicts (JSON API compatible), bypassing LLM extraction entirely. Goes straight to entity resolution + Z3 verification. Supports `system_time` for temporal rules.
- **Negation Rules** — `type: negation` with `must_not_include` for human-readable prohibitions. Single value or list. Z3 proves forbidden values never appear. Auto-wraps string to list.
- **Conditional Forbid** — Dependency rules now support `then.forbid` alongside `then.require`. When condition is met, specified values are forbidden (e.g., allergy cross-reactivity).
- **Extraction Bias Audit** — `audit_extraction_bias()` performs deterministic keyword check for protected attributes (gender, race, religion, age, disability) in extracted claims. No LLM — pure pattern matching. Customizable attribute sets.
- **Confidence Scoring** — `Claim.confidence` field (0.0-1.0). `score_claim_confidence()` detects hedge words ("maybe", "probably", "appears") and lowers confidence to 0.3. `filter_low_confidence()` splits claims for human review vs Z3.
- **Enhanced Normalization** — `normalize_enhanced()` strips titles (Dr., Prof.), suffixes (Jr., PhD, Inc.), and articles (the, a, an) deterministically.
- **Claim Classification** — `RelationDef` in YAML with `category: definitional | contingent | normative_risk` (Resnik 2025). `KnowledgeBase.relation_category()` accessor. Optional and backward compatible.
- **Tournament Mode Engine** — Multi-strategy candidate generation, Z3 conflict detection, human arbitration (v0.7.0 feature, engine ready). 36 tests.

### Research
- Tournament-style rule derivation research doc (`docs/research/v070_tournament_rule_derivation.md`)
- Roadmap updated with Resnik (2025) bias insights across v0.6.0–v1.0.0

### Changed
- Test count: 71 → 233 (162 new tests)
- `ThenClause` now supports optional `require` and `forbid` (was require-only)
- `Rule` union includes `NegationRule` and `TemporalRule`
- `KnowledgeBase.verify()` accepts optional `system_time` parameter

---

## [0.5.1] - 2026-03-28

### Added
- **Programmatic Rules** — `RuleBuilder` fluent API for building rules from code, databases, or APIs at runtime
- `generate_rules()` (deprecated — see architectural pivot in v0.5.1+)
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
