"""
AxiomGuard Backend — OpenAI (GPT-4o, GPT-4o-mini, etc.)

Usage:
    from axiomguard import set_llm_backend
    from axiomguard.backends.openai_llm import openai_translator

    set_llm_backend(openai_translator)

Requires:
    pip install openai
    export OPENAI_API_KEY="sk-..."
"""

from __future__ import annotations

import os

from axiomguard.backends import SYSTEM_PROMPT, parse_response

DEFAULT_MODEL = "gpt-4o-mini"


def create_openai_translator(
    model: str | None = None,
    api_key: str | None = None,
) -> callable:
    """Factory: create a translator bound to a specific model and API key.

    Args:
        model: OpenAI model ID. Defaults to AXIOMGUARD_OPENAI_MODEL env var
               or gpt-4o-mini.
        api_key: OpenAI API key. Defaults to OPENAI_API_KEY env var.
    """
    resolved_model = model or os.environ.get("AXIOMGUARD_OPENAI_MODEL", DEFAULT_MODEL)
    _client = None

    def _translate(text: str) -> dict:
        nonlocal _client
        if _client is None:
            from openai import OpenAI
            _client = OpenAI(api_key=api_key) if api_key else OpenAI()

        response = _client.chat.completions.create(
            model=resolved_model,
            max_tokens=150,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": text},
            ],
        )
        return parse_response(response.choices[0].message.content)

    return _translate


openai_translator = create_openai_translator()
