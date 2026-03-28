"""
AxiomGuard Backend — Anthropic Claude

Usage:
    from axiomguard import set_llm_backend
    from axiomguard.backends.anthropic_llm import anthropic_translator

    set_llm_backend(anthropic_translator)

Requires:
    pip install anthropic
    export ANTHROPIC_API_KEY="sk-ant-..."
"""

from __future__ import annotations

import os

from axiomguard.backends import SYSTEM_PROMPT, parse_response

DEFAULT_MODEL = "claude-haiku-4-5-20251001"


def create_anthropic_translator(
    model: str | None = None,
    api_key: str | None = None,
) -> callable:
    """Factory: create a translator bound to a specific model and API key.

    Args:
        model: Anthropic model ID. Defaults to AXIOMGUARD_MODEL env var
               or claude-haiku-4-5-20251001.
        api_key: Anthropic API key. Defaults to ANTHROPIC_API_KEY env var.
    """
    resolved_model = model or os.environ.get("AXIOMGUARD_MODEL", DEFAULT_MODEL)
    _client = None

    def _translate(text: str) -> dict:
        nonlocal _client
        if _client is None:
            from anthropic import Anthropic
            _client = Anthropic(api_key=api_key) if api_key else Anthropic()

        message = _client.messages.create(
            model=resolved_model,
            max_tokens=150,
            system=SYSTEM_PROMPT,
            messages=[{"role": "user", "content": text}],
        )
        return parse_response(message.content[0].text)

    return _translate


anthropic_translator = create_anthropic_translator()
