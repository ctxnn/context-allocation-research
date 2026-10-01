from __future__ import annotations

import os
import re
from typing import Any

SECRET_KEYS = {
    "authorization",
    "api_key",
    "apikey",
    "github_token",
    "openai_api_key",
    "token",
}
SECRET_PATTERNS = (
    re.compile(r"sk-[A-Za-z0-9_-]{16,}"),
    re.compile(r"gh[pousr]_[A-Za-z0-9]{16,}"),
    re.compile(r"Bearer\s+[A-Za-z0-9._~-]{12,}", re.IGNORECASE),
)


def require_env(name: str) -> str:
    value = os.environ.get(name, "").strip()
    if not value:
        raise RuntimeError(
            f"{name} is required; export it in your shell (do not commit it)"
        )
    return value


def redact_text(value: str) -> str:
    for pattern in SECRET_PATTERNS:
        value = pattern.sub("[REDACTED]", value)
    return value


def redact(value: Any) -> Any:
    if isinstance(value, dict):
        return {
            str(key): "[REDACTED]" if str(key).lower() in SECRET_KEYS else redact(item)
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [redact(item) for item in value]
    if isinstance(value, str):
        return redact_text(value)
    return value
