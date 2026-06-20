"""Qwen client (OpenAI-compatible) for LLM-driven agents.

Talks to the Bitget Qwen hackathon proxy via the OpenAI SDK. The ``openai`` package
and a key are both optional: ``available()`` is False without a key, and callers fall
back to deterministic logic, so the whole system runs offline. No key is ever logged.
"""

from __future__ import annotations

import logging

from .config import Settings, load_settings

logger = logging.getLogger(__name__)


class QwenClient:
    """Thin OpenAI-compatible chat client for the Bitget Qwen proxy."""

    def __init__(self, api_key: str | None, base_url: str, model: str) -> None:
        self._key = api_key
        self._base = base_url
        self.model = model
        self._client = None

    def available(self) -> bool:
        return bool(self._key)

    def _ensure(self):
        if self._client is None:
            from openai import OpenAI  # optional dependency ([llm] extra)

            # bounded timeout + minimal retries so a slow/hung Qwen call fails fast and the
            # agent falls back to deterministic logic, rather than blocking on the SDK's
            # 600s default (which would freeze a tournament — or a live loop).
            self._client = OpenAI(api_key=self._key, base_url=self._base, timeout=30.0, max_retries=1)
        return self._client

    def chat(self, system: str, user: str, *, temperature: float = 0.2, max_tokens: int = 500) -> str | None:
        """Return the assistant message text, or None on any failure (never raises)."""
        if not self.available():
            return None
        try:
            client = self._ensure()
            resp = client.chat.completions.create(
                model=self.model,
                messages=[{"role": "system", "content": system}, {"role": "user", "content": user}],
                temperature=temperature,
                max_tokens=max_tokens,
            )
            return resp.choices[0].message.content
        except Exception as exc:  # network / SDK / quota — fall back deterministically
            logger.warning("Qwen chat failed: %s", exc)
            return None

    @classmethod
    def from_settings(cls, settings: Settings | None = None) -> "QwenClient":
        s = settings or load_settings()
        return cls(s.qwen_api_key, s.qwen_base_url, s.qwen_model)
