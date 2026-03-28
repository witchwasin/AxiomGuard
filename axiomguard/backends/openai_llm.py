"""
AxiomGuard Backend — OpenAI GPT (v0.2.0: Multi-Claim Extraction)

Usage:
    from axiomguard import set_llm_backend
    from axiomguard.backends.openai_llm import create_openai_extractor

    set_llm_backend(create_openai_extractor())

Requires:
    pip install openai
    export OPENAI_API_KEY="sk-..."
"""

from __future__ import annotations

import json
import os

from axiomguard.backends import SYSTEM_PROMPT, validate_and_extract
from axiomguard.models import Claim


DEFAULT_MODEL = "gpt-4o-mini"


class ExtractionError(Exception):
    """Raised when LLM output cannot be parsed into valid claims."""


def create_openai_extractor(
    model: str | None = None,
    api_key: str | None = None,
    max_retries: int = 1,
) -> callable:
    """Factory: create a multi-claim extractor bound to OpenAI GPT.

    Args:
        model: OpenAI model ID. Defaults to AXIOMGUARD_OPENAI_MODEL env var
               or gpt-4o-mini.
        api_key: OpenAI API key. Defaults to OPENAI_API_KEY env var.
        max_retries: Number of retries on parse/validation failure (default: 1).
    """
    resolved_model = model or os.environ.get("AXIOMGUARD_OPENAI_MODEL", DEFAULT_MODEL)
    _client = None

    def _extract(text: str) -> list[Claim]:
        nonlocal _client
        if _client is None:
            from openai import OpenAI
            _client = OpenAI(api_key=api_key) if api_key else OpenAI()

        last_error = None
        for attempt in range(1 + max_retries):
            try:
                messages = [
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": text},
                ]

                # On retry, append the error for self-correction
                if attempt > 0 and last_error:
                    messages.extend([
                        {"role": "assistant", "content": str(last_error)},
                        {"role": "user", "content": (
                            "Your previous output was invalid. "
                            f"Error: {last_error}. "
                            "Please return ONLY valid JSON matching the schema."
                        )},
                    ])

                response = _client.chat.completions.create(
                    model=resolved_model,
                    max_tokens=1024,
                    messages=messages,
                )

                raw = response.choices[0].message.content
                claims, _warnings = validate_and_extract(raw, source_text=text)
                return claims

            except (json.JSONDecodeError, ValueError) as e:
                last_error = e
                continue
            except Exception as e:
                raise ExtractionError(
                    f"OpenAI API error: {e}"
                ) from e

        raise ExtractionError(
            f"Failed to extract valid claims after {1 + max_retries} attempts. "
            f"Last error: {last_error}"
        )

    return _extract


# Convenience: pre-built extractor with defaults
openai_extractor = create_openai_extractor()

# v0.1.0 backward compat alias
openai_translator = openai_extractor
