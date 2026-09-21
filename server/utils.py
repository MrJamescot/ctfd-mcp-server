"""Small shared helpers: URL handling, credential redaction, cache dir."""

from __future__ import annotations

import ipaddress
import re
from typing import Any
from urllib.parse import urlsplit

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

# Well-known cloud metadata / link-local endpoints used for SSRF.
METADATA_HOSTS = {
    "169.254.169.254",
    "metadata",
    "metadata.google.internal",
    "metadata.google.internal.",
    "instance-data",
    "instance-data.ec2.internal",
}


def mask(value: Any) -> str:
    """Return a redacted representation of a secret.

    Always returns a placeholder: secrets are never echoed, not even
    partially, into output or persisted state.
    """
    return "" if value in (None, "") else REDACTED


def sanitize(obj: Any, secrets: tuple[str, ...] = ()) -> Any:
    """Deep-copy ``obj`` redacting sensitive values.

    Values whose key is in ``SENSITIVE_KEYS`` are replaced by REDACTED, and any
    occurrence of a *known secret value* (from ``secrets``) inside string fields
    is also scrubbed so tokens embedded in URLs or error text never leak.
    """
    secrets = tuple(s for s in secrets if s)
    if isinstance(obj, dict):
        result: dict[str, Any] = {}
        for key, val in obj.items():
            lowered = key.lower()
            if lowered in SENSITIVE_KEYS:
                result[key] = REDACTED
            elif isinstance(val, str):
                result[key] = scrub(val, secrets)
            else:
                result[key] = sanitize(val, secrets)
        return result
    if isinstance(obj, (list, tuple)):
        return [sanitize(item, secrets) for item in obj]
    if isinstance(obj, str) and secrets:
        return scrub(obj, secrets)
    return obj


def scrub(value: str, secrets: tuple[str, ...]) -> str:
    """Replace every occurrence of each known secret with REDACTED."""
    for secret in secrets:
        if secret and secret in value:
            value = value.replace(secret, REDACTED)
    return value


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


def is_private_or_metadata_url(value: str) -> bool:
    """True when ``value`` targets a private/loopback/link-local address,
    a cloud metadata endpoint, or a bare localhost hostname.

    Used to block SSRF: a public MCP/REST server must not let callers point it
    at internal hosts (127.0.0.1, 10.x/172.16-31.x/192.168.x, 169.254.169.254,
    *.localhost, ...) unless ``CTFD_ALLOW_PRIVATE_IPS=1`` is set.
    """
    host = (urlsplit(value.strip().rstrip("/")).hostname or "").lower().rstrip(".")
    if not host:
        return False
    if host in METADATA_HOSTS or host == "localhost" or host.endswith(".localhost"):
        return True
    try:
        ip = ipaddress.ip_address(host)
    except ValueError:
        # A DNS name: nothing to resolve here; it is allowed.
        return False
    return (
        ip.is_private
        or ip.is_loopback
        or ip.is_link_local
        or ip.is_reserved
        or ip.is_multicast
        or ip.is_unspecified
    )


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