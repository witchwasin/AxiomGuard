# Installation

## Basic Install

```bash
pip install axiomguard
```

This installs the core package with Z3 verification. Works immediately with the built-in mock backend — **no API key needed**.

## With LLM Backends

For production use with real LLM-powered extraction:

=== "Anthropic (Claude)"

    ```bash
    pip install "axiomguard[anthropic]"
    ```

=== "OpenAI (GPT-4o)"

    ```bash
    pip install "axiomguard[openai]"
    ```

=== "Everything"

    ```bash
    pip install "axiomguard[all]"
    ```

    Includes: Anthropic, OpenAI, ChromaDB, Qdrant

## From Source (Development)

```bash
git clone https://github.com/witchwasin/AxiomGuard.git
cd AxiomGuard
pip install -e ".[all,dev]"
pytest tests/
```

## Requirements

- **Python:** 3.9+
- **Z3 Solver:** Installed automatically via `z3-solver` pip package
- **OS:** Linux, macOS, Windows

## Verify Installation

```python
import axiomguard
print(axiomguard.__version__)  # 0.5.0
```
