from __future__ import annotations

import re

REDACTED_TOKEN = "<REDACTED>"
TRUNCATED_SUFFIX = "...[truncated]"

_KEYS_TO_REDACT_KV = (
    "user_message",
    "assistant_message",
    "token",
    "password",
    "passwd",
    "secret",
    "api_key",
    "authorization",
)

_KEYS_PATTERN_KV = "|".join(re.escape(k) for k in _KEYS_TO_REDACT_KV)

_JSON_RE = re.compile(
    r'(?i)"(' + _KEYS_PATTERN_KV + r')"\s*:\s*("[^"]*")'
)

_KV_RE = re.compile(
    r'(?i)\b(' + _KEYS_PATTERN_KV + r')(\s*[:=]\s*)("[^"]*"|\'[^\']*\'|\S+)'
)

_AUTH_BEARER_RE = re.compile(
    r'(?i)(authorization\s*:\s*)Bearer\s+[A-Za-z0-9._\-+/=]+'
)

_BEARER_RE = re.compile(
    r'(?i)(bearer)\s+([A-Za-z0-9._\-+/=]+)'
)


def _redact_sensitive(text: str) -> str:
    text = _AUTH_BEARER_RE.sub(r'\1<REDACTED>', text)
    text = _JSON_RE.sub(r'"\1": <REDACTED>', text)
    text = _KV_RE.sub(r'\1\2<REDACTED>', text)
    text = _BEARER_RE.sub(r'\1 <REDACTED>', text)
    return text


def sanitize_error_message(
    message: str | None,
    *,
    max_length: int = 4096,
) -> str:
    if message is None:
        return ""
    if not message:
        return ""
    result = _redact_sensitive(message)
    if len(result) > max_length:
        trunc_at = max_length - len(TRUNCATED_SUFFIX)
        if trunc_at < 0:
            trunc_at = 0
        result = result[:trunc_at] + TRUNCATED_SUFFIX
    return result


def sanitize_exception(
    error: BaseException,
    *,
    max_length: int = 4096,
) -> str:
    return sanitize_error_message(str(error), max_length=max_length)
