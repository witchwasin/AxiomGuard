# Contributing to AxiomGuard

Thanks for your interest in AxiomGuard! This guide will help you get started.

---

## Development Setup

```bash
# Clone the repository
git clone https://github.com/witchwasin/AxiomGuard.git
cd AxiomGuard

# Install in editable mode with all extras
pip install -e ".[all,dev]"

# Verify installation
python -c "import axiomguard; print(axiomguard.__version__)"

# Run tests
pytest tests/
```

### Requirements

- Python 3.9+
- Z3 Solver (installed automatically via `z3-solver` pip package)

---

## Running Tests

```bash
# Run all tests
pytest tests/

# Run with verbose output
pytest tests/ -v

# Run a specific test file
pytest tests/test_z3_engine.py

# Run with coverage
pytest tests/ --cov=axiomguard --cov-report=term-missing
```

All PRs must pass existing tests. Add new tests for new features.

---

## Project Structure

```
axiomguard/
├── core.py              # Main orchestration (extract → resolve → verify)
├── z3_engine.py         # Z3 SMT solver integration
├── models.py            # Claim, VerificationResult, CorrectionResult
├── knowledge_base.py    # YAML rule loading & KnowledgeBase
├── parser.py            # .axiom.yml → rule objects
├── correction.py        # Self-correction prompt builder
├── resolver.py          # Entity normalization (fuzzy matching)
├── integration.py       # Vector DB integration layer
└── backends/            # LLM provider implementations
    ├── anthropic_llm.py
    ├── openai_llm.py
    └── generic_http_llm.py
```

---

## Commit Conventions

We follow [Conventional Commits](https://www.conventionalcommits.org/):

```
feat(core): add temporal logic rules
fix(resolver): handle empty entity names
docs: update quickstart example
test: add negation handling tests
chore: bump z3-solver to 4.13.0
```

**Scopes:** `core`, `z3`, `kb`, `parser`, `resolver`, `correction`, `backends`, `integrations`

---

## Pull Request Process

1. **Fork** the repository and create a feature branch from `main`
2. **Write tests** for any new functionality
3. **Run the full test suite** — all tests must pass
4. **Keep PRs focused** — one feature or fix per PR
5. **Write a clear PR description** — what changed, why, and how to test it

---

## Where to Contribute

### High Impact

| Area | Description |
|------|-------------|
| **NL-to-Logic translation** | Improve entity normalization, handle complex sentence structures |
| **New rule types** | Numeric comparisons, temporal logic, negation, cardinality |
| **Benchmarks** | Test against real-world hallucination datasets (HaluEval, TruthfulQA) |

### Medium Impact

| Area | Description |
|------|-------------|
| **New LLM backends** | Google Gemini, Mistral, Cohere, AWS Bedrock |
| **Vector DB integrations** | Pinecone, Weaviate, Milvus |
| **Performance** | Caching, parallel verification, Z3 solver tuning |

### Quick Wins

| Area | Description |
|------|-------------|
| **Examples** | New `.axiom.yml` rule files for different domains |
| **Documentation** | Tutorials, blog posts, video walkthroughs |
| **Bug reports** | Open an issue with reproduction steps |

---

## Coding Guidelines

- **Type hints** on all public functions
- **Pydantic models** for validated data (LLM outputs, extraction results)
- **Dataclasses** for internal data (verification results, correction attempts)
- **Docstrings** on public classes and functions
- Keep the core principle: **ML handles language, Math handles truth**

---

## Reporting Bugs

Open a [GitHub Issue](https://github.com/witchwasin/AxiomGuard/issues) with:

1. Python version and OS
2. AxiomGuard version (`python -c "import axiomguard; print(axiomguard.__version__)"`)
3. Minimal reproduction code
4. Expected vs actual behavior

---

## License

By contributing, you agree that your contributions will be licensed under the [MIT License](LICENSE).
