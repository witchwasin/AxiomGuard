# API Key Setup

## Do I Need an API Key?

**Not always.** It depends on what you use:

| Feature | API Key Required? |
|---------|:-----------------:|
| `verify()` with simple sentences | No (mock backend) |
| `verify_with_kb()` with YAML rules | No |
| `RuleBuilder` (programmatic rules) | No |
| `generate_rules()` (AI-generated rules) | **Yes** |
| `generate_with_guard()` (self-correction) | **Yes** |
| Real LLM extraction (complex sentences) | **Yes** |

## Setting Up

=== "Anthropic (Claude) — Recommended"

    ```bash
    export ANTHROPIC_API_KEY="sk-ant-api03-..."
    ```

    Get your key at [console.anthropic.com](https://console.anthropic.com/)

=== "OpenAI (GPT-4o)"

    ```bash
    export OPENAI_API_KEY="sk-..."
    ```

    Get your key at [platform.openai.com](https://platform.openai.com/)

=== "Local LLM (Ollama)"

    No API key needed. Just install and run Ollama:

    ```bash
    # Install Ollama
    curl -fsSL https://ollama.ai/install.sh | sh

    # Pull a model
    ollama pull llama3.1

    # Use in AxiomGuard
    ```

    ```python
    from axiomguard.backends.generic_http_llm import create_http_translator
    import axiomguard

    axiomguard.set_llm_backend(create_http_translator(model="llama3.1"))
    ```

## Persistent Setup

Add to your shell profile (`~/.bashrc`, `~/.zshrc`):

```bash
# ~/.zshrc
export ANTHROPIC_API_KEY="sk-ant-api03-..."
```

Then reload: `source ~/.zshrc`

!!! info "Each user provides their own key"
    No API keys are bundled with the package. Each user sets up their own key and pays for their own usage.
