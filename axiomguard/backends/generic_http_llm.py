"""
AxiomGuard Backend — Generic HTTP (v0.2.0: Multi-Claim Extraction)

Supports Ollama, vLLM, LM Studio, and any OpenAI-compatible API endpoint.

Usage:
    from axiomguard import set_llm_backend
    from axiomguard.backends.generic_http_llm import create_http_extractor

    # Ollama (default: http://localhost:11434)
    set_llm_backend(create_http_extractor(model="llama3.1"))

    # Custom endpoint
    set_llm_backend(create_http_extractor(
        base_url="http://my-server:8080/v1",
        model="my-model",
        api_key="optional-key",
    ))

Requires:
    No extra dependencies — uses httpx (already installed with anthropic/openai).
    Falls back to urllib if httpx is not available.
"""

from __future__ import annotations

import json

from axiomguard.backends import SYSTEM_PROMPT, validate_and_extract
from axiomguard.models import Claim


DEFAULT_BASE_URL = "http://localhost:11434/v1"
DEFAULT_MODEL = "llama3.1"


class ExtractionError(Exception):
    """Raised when LLM output cannot be parsed into valid claims."""


def create_http_extractor(
    base_url: str | None = None,
    model: str | None = None,
    api_key: str | None = None,
    max_retries: int = 1,
) -> callable:
    """Factory: create a multi-claim extractor for any OpenAI-compatible endpoint.

    Args:
        base_url: API base URL. Defaults to http://localhost:11434/v1 (Ollama).
        model: Model name as recognized by the server.
        api_key: Optional API key (some endpoints require it).
        max_retries: Number of retries on parse/validation failure (default: 1).
    """
    resolved_url = (base_url or DEFAULT_BASE_URL).rstrip("/")
    resolved_model = model or DEFAULT_MODEL
    endpoint = f"{resolved_url}/chat/completions"

    _client = None  # None = not yet initialized, False = use urllib fallback

    def _extract(text: str) -> list[Claim]:
        nonlocal _client

        if _client is None:
            try:
                import httpx
                _client = httpx.Client(timeout=30.0)
            except ImportError:
                _client = False  # sentinel: use urllib fallback

        headers = {"Content-Type": "application/json"}
        if api_key:
            headers["Authorization"] = f"Bearer {api_key}"

        last_error = None
        for attempt in range(1 + max_retries):
            try:
                messages = [
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": text},
                ]

                if attempt > 0 and last_error:
                    messages.extend([
                        {"role": "assistant", "content": str(last_error)},
                        {"role": "user", "content": (
                            "Your previous output was invalid. "
                            f"Error: {last_error}. "
                            "Please return ONLY valid JSON matching the schema."
                        )},
                    ])

                payload = json.dumps({
                    "model": resolved_model,
                    "max_tokens": 1024,
                    "messages": messages,
                })

                if _client:
                    resp = _client.post(endpoint, content=payload, headers=headers)
                    resp.raise_for_status()
                    data = resp.json()
                else:
                    import urllib.request
                    req = urllib.request.Request(
                        endpoint,
                        data=payload.encode(),
                        headers=headers,
                        method="POST",
                    )
                    with urllib.request.urlopen(req, timeout=30) as resp:
                        data = json.loads(resp.read().decode())

                raw = data["choices"][0]["message"]["content"]
                claims, _warnings = validate_and_extract(raw, source_text=text)
                return claims

            except (json.JSONDecodeError, ValueError) as e:
                last_error = e
                continue
            except Exception as e:
                raise ExtractionError(
                    f"HTTP backend error ({endpoint}): {e}"
                ) from e

        raise ExtractionError(
            f"Failed to extract valid claims after {1 + max_retries} attempts. "
            f"Last error: {last_error}"
        )

    return _extract
