"""Small shared helpers: URL handling, credential redaction, cache dir."""

from __future__ import annotations

import os
import re
from typing import Any
from urllib.parse import urlsplit

from .config import settings

REDACTED = "[REDACTED]"

# Dict keys whose values must never appear in output or persisted state.
SENSITIVE_KEYS = {
    "token",
    "cookie",
    "password",
    "authorization",
    "set-cookie",
    "session",
    "nonce",
    "csrf",
    "csrf_token",
    "csrf_nonce",
    "flag",
    "submission",
    "answer",
}


def ensure_cache_dir() -> None:
    """Create the challenge-file cache directory if it does not exist yet."""
    os.makedirs(settings.file_cache_dir, exist_ok=True)


def mask(value: Any) -> str:
    """Return a redacted representation of a secret.

    Always returns a placeholder: secrets are never echoed, not even
    partially, into output or persisted state.
    """
    return "" if value in (None, "") else REDACTED


def sanitize(obj: Any) -> Any:
    """Deep-copy ``obj`` with every sensitive value replaced by REDACTED."""
    if isinstance(obj, dict):
        return {
            key: REDACTED if key.lower() in SENSITIVE_KEYS else sanitize(val)
            for key, val in obj.items()
        }
    if isinstance(obj, (list, tuple)):
        return [sanitize(item) for item in obj]
    return obj


def safe_host(base_url: str) -> str:
    """Return a human friendly but safe (credential-free) host label."""
    if not base_url:
        return "<unconfigured>"
    parts = urlsplit(base_url)
    return parts.netloc or base_url


def api_base(base_url: str) -> str:
    """Return ``base_url + "/api/v1"`` (without duplicating an existing suffix)."""
    base = base_url.rstrip("/")
    if base.endswith("/api"):
        return base + "/v1"
    if re.search(r"/api/v\d+$", base):
        return base
    return base + "/api/v1"


def is_valid_http_url(value: str) -> bool:
    """Validate an absolute http(s) URL without userinfo/query/fragment."""
    parts = urlsplit(value.strip().rstrip("/"))
    if parts.scheme not in ("http", "https") or not parts.netloc:
        return False
    return not (parts.query or parts.fragment or "@" in parts.netloc)


def extract_csrf_nonce(html: str) -> str | None:
    """Best-effort extraction of CTFd's CSRF nonce from a rendered page.

    Newer CTFd themes embed the nonce in ``window.init.csrfNonce``; older
    themes render a hidden ``csrf_token`` form field.  Returns ``None`` when
    neither pattern is found.
    """
    patterns = (
        r"[cC]srf[Nn]once['\"]?\s*[:=]\s*['\"]([0-9a-fA-F]+)['\"]",
        r'name=["\']csrf_token["\'][^>]*value=["\']([^"\']+)["\']',
    )
    for pattern in patterns:
        match = re.search(pattern, html)
        if match:
            return match.group(1)
    return None


def extract_version(html: str) -> str | None:
    """Best-effort detection of a CTFd version string in a rendered page.

    CTFd does not expose a stable public version endpoint, so this only
    reports a version when one is clearly present in the page markup.
    """
    patterns = (
        r"CTFd[\s\S]{0,20}?v?(\d+\.\d+(?:\.\d+)?)",
        r"data-version=[\"']v?(\d+\.\d+(?:\.\d+)?)[\"']",
    )
    for pattern in patterns:
        match = re.search(pattern, html)
        if match:
            return match.group(1)
    return None