# LLM Backends

AxiomGuard is **provider-agnostic**. The Z3 verification engine is always the same — only the NL-to-Logic translator changes. Swap backends in one line.

## Available Backends

| Backend | Package | API Key | Quality |
|---------|---------|---------|---------|
| Mock (built-in) | None | None | Simple sentences only |
| Anthropic (Claude) | `axiomguard[anthropic]` | `ANTHROPIC_API_KEY` | Excellent |
| OpenAI (GPT-4o) | `axiomguard[openai]` | `OPENAI_API_KEY` | Excellent |
| Local (Ollama/vLLM) | None | None | Good (model-dependent) |
| Custom | None | Varies | You decide |

## Anthropic (Claude)

```bash
pip install "axiomguard[anthropic]"
export ANTHROPIC_API_KEY="sk-ant-..."
```

```python
import axiomguard
from axiomguard.backends.anthropic_llm import anthropic_translator

axiomguard.set_llm_backend(anthropic_translator)
```

Specify a model:

```python
from axiomguard.backends.anthropic_llm import create_anthropic_translator

backend = create_anthropic_translator(model="claude-sonnet-4-5-20250514")
axiomguard.set_llm_backend(backend)
```

## OpenAI (GPT-4o)

```bash
pip install "axiomguard[openai]"
export OPENAI_API_KEY="sk-..."
```

```python
import axiomguard
from axiomguard.backends.openai_llm import openai_translator

axiomguard.set_llm_backend(openai_translator)
```

## Local LLMs (Ollama / vLLM)

No API key needed. Works with any OpenAI-compatible endpoint:

```python
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

## Custom Backend

Any function `(str) -> dict` works:

```python
import axiomguard

def my_backend(text: str) -> dict:
    # Your logic — call any API, model, or rule engine
    return {"subject": "company", "relation": "location", "object": "Bangkok"}

axiomguard.set_llm_backend(my_backend)
```
