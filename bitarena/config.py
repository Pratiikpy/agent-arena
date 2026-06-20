"""Runtime configuration, loaded from environment variables (.env supported).

Kept deliberately dependency-light: a frozen dataclass over ``os.environ`` with an
optional ``python-dotenv`` load. No secret is ever logged or echoed.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

try:  # optional: load a local .env if present
    from dotenv import load_dotenv

    load_dotenv()
except Exception:  # pragma: no cover - dotenv is optional
    pass


def _get(name: str, default: str | None = None) -> str | None:
    value = os.environ.get(name)
    return value if value not in (None, "") else default


@dataclass(frozen=True)
class Settings:
    """Resolved runtime settings. All credential fields may be ``None`` offline."""

    bitget_api_key: str | None
    bitget_secret_key: str | None
    bitget_passphrase: str | None
    qwen_api_key: str | None
    qwen_base_url: str
    qwen_model: str
    signing_key_path: Path
    signing_key_b64: str | None
    mode: str

    @property
    def has_bitget_keys(self) -> bool:
        return bool(self.bitget_api_key and self.bitget_secret_key and self.bitget_passphrase)

    @property
    def has_qwen(self) -> bool:
        return bool(self.qwen_api_key)


def load_settings() -> Settings:
    """Build a :class:`Settings` snapshot from the current environment."""
    return Settings(
        bitget_api_key=_get("BITGET_API_KEY"),
        bitget_secret_key=_get("BITGET_SECRET_KEY"),
        bitget_passphrase=_get("BITGET_PASSPHRASE"),
        qwen_api_key=_get("BITGET_QWEN_API_KEY") or _get("QWEN_API_KEY"),
        qwen_base_url=_get("QWEN_BASE_URL", "https://hackathon.bitgetops.com/v1"),
        qwen_model=_get("QWEN_MODEL", "qwen3.6-plus"),
        signing_key_path=Path(_get("ARENA_SIGNING_KEY_PATH", ".keys/arena_ed25519.pem")),
        signing_key_b64=_get("ARENA_SIGNING_KEY_B64"),
        mode=_get("ARENA_MODE", "paper"),
    )
