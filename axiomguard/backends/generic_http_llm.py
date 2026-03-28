"""
AxiomGuard Backend — Generic HTTP (Ollama, vLLM, LM Studio, any OpenAI-compatible API)

Usage:
    from axiomguard import set_llm_backend
    from axiomguard.backends.generic_http_llm import create_http_translator

    # Ollama (default: http://localhost:11434)
    set_llm_backend(create_http_translator(model="llama3.1"))

    # Custom endpoint
    set_llm_backend(create_http_translator(
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

from axiomguard.backends import SYSTEM_PROMPT, parse_response

DEFAULT_BASE_URL = "http://localhost:11434/v1"
DEFAULT_MODEL = "llama3.1"


def create_http_translator(
    base_url: str | None = None,
    model: str | None = None,
    api_key: str | None = None,
) -> callable:
    """Factory: create a translator for any OpenAI-compatible HTTP endpoint.

    Most local LLM servers (Ollama, vLLM, LM Studio, text-generation-inference)
    expose an OpenAI-compatible /v1/chat/completions endpoint.

    Args:
        base_url: API base URL. Defaults to http://localhost:11434/v1 (Ollama).
        model: Model name as recognized by the server.
        api_key: Optional API key (some endpoints require it).
    """
    resolved_url = (base_url or DEFAULT_BASE_URL).rstrip("/")
    resolved_model = model or DEFAULT_MODEL
    endpoint = f"{resolved_url}/chat/completions"

    _client = None  # None = not yet initialized, False = use urllib fallback

    def _translate(text: str) -> dict:
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

        payload = json.dumps({
            "model": resolved_model,
            "max_tokens": 150,
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": text},
            ],
        })

        if _client:
            # httpx path
            resp = _client.post(endpoint, content=payload, headers=headers)
            resp.raise_for_status()
            data = resp.json()
        else:
            # stdlib fallback
            import urllib.request
            req = urllib.request.Request(
                endpoint,
                data=payload.encode(),
                headers=headers,
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=30) as resp:
                data = json.loads(resp.read().decode())

        return parse_response(data["choices"][0]["message"]["content"])

    return _translate
