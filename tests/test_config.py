"""Tests for configuration validation and URL handling."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from server.config import Settings
from server.utils import (
    api_base,
    extract_csrf_nonce,
    extract_version,
    is_valid_http_url,
    mask,
    safe_host,
    sanitize,
)


@pytest.mark.parametrize(
    "url",
    [
        "https://ctf.example.com",
        "https://ctf.example.com/ctfd",
        "http://localhost:8000",
        "http://127.0.0.1:9999",
    ],
)
def test_valid_base_urls(url):
    settings = Settings(_env_file=None, ctfd_base_url=url)
    assert settings.ctfd_base_url.rstrip("/")


@pytest.mark.parametrize(
    "url",
    [
        "not a url",
        "ftp://ctf.example.com",
        "https://ctf.example.com?page=2",
        "https://ctf.example.com#frag",
        "https://user:pass@ctf.example.com",
        "https://",
    ],
)
def test_invalid_base_urls(url):
    with pytest.raises(ValidationError):
        Settings(_env_file=None, ctfd_base_url=url)


def test_timeout_validation():
    with pytest.raises(ValidationError):
        Settings(_env_file=None, http_timeout=0)


def test_transport_validation():
    with pytest.raises(ValidationError):
        Settings(_env_file=None, mcp_transport="udp")


def test_env_var_mapping(monkeypatch):
    """Documented CTFD_* env vars must map to the right settings fields."""
    env = {
        "CTFD_BASE_URL": "https://ctf.example.com",
        "CTFD_ADMIN_TOKEN": "ctfd_abc",
        "CTFD_SESSION_COOKIE": "session=xyz",
        "CTFD_HTTP_TIMEOUT": "30",
        "FILE_CACHE_DIR": "/tmp/cache",
        "CTFD_MCP_TRANSPORT": "sse",
        "MCP_PORT": "9001",
        "CTFD_PERSIST_SECRETS": "true",
    }
    monkeypatch.setenv("_PYTEST_DISABLE_DOTENV", "1")
    for k, v in env.items():
        monkeypatch.setenv(k, v)
    settings = Settings(_env_file=None)
    assert settings.ctfd_base_url == "https://ctf.example.com"
    assert settings.ctfd_admin_token == "ctfd_abc"
    assert settings.ctfd_session_cookie == "session=xyz"
    assert settings.http_timeout == 30.0
    assert settings.file_cache_dir == "/tmp/cache"
    assert settings.mcp_transport == "sse"
    assert settings.mcp_port == 9001
    assert settings.persist_secrets is True


def test_is_valid_http_url():
    assert is_valid_http_url("https://ctf.example.com")
    assert is_valid_http_url("http://localhost:9000")
    assert not is_valid_http_url("javascript:alert(1)")
    assert not is_valid_http_url("file:///etc/passwd")
    assert not is_valid_http_url("https://user:pw@host/")
    assert not is_valid_http_url("https://host/?x=1")


def test_api_base_suffix_handling():
    assert api_base("https://ctf.example.com") == "https://ctf.example.com/api/v1"
    assert api_base("https://ctf.example.com/ctfd") == "https://ctf.example.com/ctfd/api/v1"
    assert api_base("https://ctf.example.com/api/v1") == "https://ctf.example.com/api/v1"


def test_mask_never_returns_secret():
    assert mask("abcdefgh-secret1234") == "[REDACTED]"
    assert mask(None) == ""
    assert mask("") == ""
    assert mask("x" * 30) == "[REDACTED]"


def test_sanitize_redacts_secrets():
    data = {"token": "ctfd_secret", "data": {"password": "hunter2", "ok": 1}, "flag": "flag{x}"}
    cleaned = sanitize(data)
    assert cleaned["token"] == "[REDACTED]"
    assert cleaned["data"]["password"] == "[REDACTED]"
    assert cleaned["data"]["ok"] == 1
    assert cleaned["flag"] == "[REDACTED]"


def test_safe_host():
    assert safe_host("https://ctf.example.com/path") == "ctf.example.com"
    assert safe_host("") == "<unconfigured>"


def test_extract_csrf_nonce():
    html = "<script>window.init = { 'csrfNonce': \"aabbccdd0011\", 'userId': 0 }</script>"
    assert extract_csrf_nonce(html) == "aabbccdd0011"
    form_html = '<input type="hidden" name="csrf_token" value="feedbeef01" />'
    assert extract_csrf_nonce(form_html) == "feedbeef01"
    assert extract_csrf_nonce("<html>nothing here</html>") is None


def test_extract_version():
    assert extract_version("... CTFd v3.5.3 all rights reserved ...") == "3.5.3"
    assert extract_version("no version here") is None