"""Secret scrubbing utilities for trace-safe logging."""

from __future__ import annotations

import re
from typing import Any

# Pattern list — order matters, more specific first.
SECRET_PATTERNS: list[tuple[str, str]] = [
    (r"sk-ant-[a-zA-Z0-9\-_]{20,}", "[REDACTED:anthropic-key]"),
    (r"sk-or-v1-[a-zA-Z0-9]{20,}", "[REDACTED:openrouter-key]"),
    (r"sk-[a-zA-Z0-9]{20,}", "[REDACTED:openai-key]"),
    (r"gsk_[a-zA-Z0-9]{20,}", "[REDACTED:groq-key]"),
    (r"gh[pousr]_[a-zA-Z0-9]{36,}", "[REDACTED:github-token]"),
    (r"AKIA[0-9A-Z]{16}", "[REDACTED:aws-key]"),
    (
        r"(?i)aws.{0,20}secret.{0,20}['\"]([a-zA-Z0-9+/]{40})['\"]",
        "[REDACTED:aws-secret]",
    ),
    (r"Bearer\s+[a-zA-Z0-9\-._~+/]{20,}=*", "Bearer [REDACTED]"),
]

_COMPILED: list[tuple[re.Pattern[str], str]] = [
    (re.compile(pattern), replacement) for pattern, replacement in SECRET_PATTERNS
]


def scrub(text: str) -> str:
    """Apply all secret patterns in order and return a scrubbed string."""
    scrubbed = text
    for pattern, replacement in _COMPILED:
        scrubbed = pattern.sub(replacement, scrubbed)
    return scrubbed


def _scrub_value(value: Any) -> Any:
    if isinstance(value, str):
        return scrub(value)
    if isinstance(value, dict):
        return scrub_dict(value)
    if isinstance(value, list):
        return [_scrub_value(item) for item in value]
    return value


def scrub_dict(data: dict[str, Any]) -> dict[str, Any]:
    """Recursively scrub all string values in a dict and return a new dict."""
    return {key: _scrub_value(value) for key, value in data.items()}
