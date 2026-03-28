"""
AxiomGuard Backend — Anthropic Claude (v0.2.0: Multi-Claim Extraction)

Usage:
    from axiomguard import set_llm_backend
    from axiomguard.backends.anthropic_llm import create_anthropic_extractor

    set_llm_backend(create_anthropic_extractor())

Requires:
    pip install anthropic
    export ANTHROPIC_API_KEY="sk-ant-..."
"""

from __future__ import annotations

import json
import os

from axiomguard.backends import SYSTEM_PROMPT, validate_and_extract
from axiomguard.models import Claim


DEFAULT_MODEL = "claude-haiku-4-5-20251001"


class ExtractionError(Exception):
    """Raised when LLM output cannot be parsed into valid claims."""


def create_anthropic_extractor(
    model: str | None = None,
    api_key: str | None = None,
    max_retries: int = 1,
) -> callable:
    """Factory: create a multi-claim extractor bound to Anthropic Claude.

    Args:
        model: Anthropic model ID. Defaults to AXIOMGUARD_MODEL env var
               or claude-haiku-4-5-20251001.
        api_key: Anthropic API key. Defaults to ANTHROPIC_API_KEY env var.
        max_retries: Number of retries on parse/validation failure (default: 1).
    """
    resolved_model = model or os.environ.get("AXIOMGUARD_MODEL", DEFAULT_MODEL)
    _client = None

    def _extract(text: str) -> list[Claim]:
        nonlocal _client
        if _client is None:
            from anthropic import Anthropic
            _client = Anthropic(api_key=api_key) if api_key else Anthropic()

        last_error = None
        for attempt in range(1 + max_retries):
            try:
                messages = [{"role": "user", "content": text}]

                # On retry, append the error so the LLM can self-correct
                if attempt > 0 and last_error:
                    messages = [
                        {"role": "user", "content": text},
                        {"role": "assistant", "content": str(last_error)},
                        {"role": "user", "content": (
                            "Your previous output was invalid. "
                            f"Error: {last_error}. "
                            "Please return ONLY valid JSON matching the schema."
                        )},
                    ]

                message = _client.messages.create(
                    model=resolved_model,
                    max_tokens=1024,
                    system=SYSTEM_PROMPT,
                    messages=messages,
                )

                raw = message.content[0].text
                claims, _warnings = validate_and_extract(raw, source_text=text)
                return claims

            except (json.JSONDecodeError, ValueError) as e:
                last_error = e
                continue
            except Exception as e:
                # API errors (rate limit, auth, network) — don't retry
                raise ExtractionError(
                    f"Anthropic API error: {e}"
                ) from e

        raise ExtractionError(
            f"Failed to extract valid claims after {1 + max_retries} attempts. "
            f"Last error: {last_error}"
        )

    return _extract


# Convenience: pre-built extractor with defaults
anthropic_extractor = create_anthropic_extractor()

# v0.1.0 backward compat alias
anthropic_translator = anthropic_extractor
