"""OpenRouter chat-completions client (OpenAI-compatible API).

Docs: https://openrouter.ai/docs/api-reference/chat-completion
"""

from __future__ import annotations

from typing import Any

import requests

from shared.settings import ENV_OPENROUTER_KEY, ai_disabled, env_value, openrouter_model

OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"
REQUEST_TIMEOUT_S = 180


class LlmError(RuntimeError):
    """Raised when the LLM call cannot be made or returns no usable answer."""


def llm_status() -> str:
    """Empty string when AI is usable, otherwise the reason it is not."""
    if ai_disabled():
        return "AI disabled (--no-ai)"
    if not env_value(ENV_OPENROUTER_KEY):
        return f"{ENV_OPENROUTER_KEY} is not set"
    return ""


def complete(prompt: str, max_tokens: int = 8000) -> str:
    """Send one user prompt to OpenRouter and return the answer text."""
    reason = llm_status()
    if reason:
        raise LlmError(reason)
    payload: dict[str, Any] = {
        "model": openrouter_model(),
        "messages": [{"role": "user", "content": prompt}],
        "max_tokens": max_tokens,
    }
    headers = {"Authorization": f"Bearer {env_value(ENV_OPENROUTER_KEY)}", "X-Title": "seo-geo-automation"}
    try:
        resp = requests.post(OPENROUTER_URL, json=payload, headers=headers, timeout=REQUEST_TIMEOUT_S)
    except requests.RequestException as exc:
        raise LlmError(f"OpenRouter request failed: {exc}") from exc
    return _answer_text(resp)


def _answer_text(resp: requests.Response) -> str:
    if resp.status_code != 200:
        raise LlmError(f"OpenRouter HTTP {resp.status_code}: {resp.text[:300]}")
    data = resp.json()
    try:
        text = str(data["choices"][0]["message"]["content"] or "").strip()
    except (KeyError, IndexError, TypeError) as exc:
        raise LlmError(f"Unexpected OpenRouter response: {str(data)[:300]}") from exc
    if not text:
        raise LlmError("OpenRouter returned an empty answer")
    return text
