"""Centralised configuration for the CTFd MCP server.

Values are read from environment variables and an optional ``.env`` file
(``python-dotenv`` / ``pydantic-settings``).  Every runtime path funnels
through this module so there is a single source of truth.
"""

from __future__ import annotations

from urllib.parse import urlsplit

from pydantic import AliasChoices, Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    # Base URL of the CTFd instance, WITHOUT the trailing "/api/v1".
    # Example: "https://ctf.example.com" or "https://ctf.example.com/ctfd".
    ctfd_base_url: str = ""

    # Optional credentials provisioned through the environment.  These are
    # loaded into memory only and are never written back to disk.
    ctfd_admin_token: str = ""
    ctfd_session_cookie: str = ""
    ctfd_username: str = ""
    ctfd_password: str = ""

    # Optional bearer token protecting the REST interface
    # (/api/v1/*).  When set, every REST call must include
    # ``Authorization: Bearer <token>``; the SSE transport is unaffected.
    ctfd_api_token: str = ""

    # SSRF guard.  Private/loopback/link-local/metadata hosts are blocked by
    # default; enable this to point the server at a local CTFd instance
    # (e.g. http://127.0.0.1:8000).
    ctfd_allow_private_ips: bool = Field(default=False, validation_alias=AliasChoices("CTFD_ALLOW_PRIVATE_IPS", "ctfd_allow_private_ips"))

    # Where non-secret runtime state is persisted.  Relative paths resolve
    # against the CWD unless overridden (recommended for containers).
    ctfd_state_file: str = Field(default="", validation_alias=AliasChoices("CTFD_STATE_FILE", "ctfd_state_file"))

    # HTTP / transport settings.
    http_timeout: float = Field(default=15.0, validation_alias=AliasChoices("CTFD_HTTP_TIMEOUT", "http_timeout"))
    http_max_redirects: int = Field(default=5, validation_alias=AliasChoices("CTFD_HTTP_MAX_REDIRECTS", "http_max_redirects"))

    # REST server bind address/port.  Defaults to loopback so the API is
    # not exposed to the network; open it up explicitly (host 0.0.0.0) and
    # protect it with CTFD_API_TOKEN when you need remote access.
    mcp_host: str = "127.0.0.1"
    mcp_port: int = 8000

    # Where challenge attachments are saved by the download_file tool.
    downloads_dir: str = Field(default="./downloads", validation_alias=AliasChoices("CTFD_DOWNLOAD_DIR", "downloads_dir"))

    # Persist credentials to server_state.json.  Keep disabled (default) so
    # secrets are never written to disk.  Enabling this is discouraged.
    persist_secrets: bool = Field(default=False, validation_alias=AliasChoices("CTFD_PERSIST_SECRETS", "persist_secrets"))

    # MCP transport: "stdio" (default, for Claude Desktop / MCP clients) or
    # "sse" (exposes the server over HTTP for remote/Docker usage).
    mcp_transport: str = Field(default="stdio", validation_alias=AliasChoices("CTFD_MCP_TRANSPORT", "mcp_transport"))

    @field_validator("ctfd_base_url")
    @classmethod
    def _validate_base_url(cls, value: str) -> str:
        if not value:
            return ""
        value = value.strip().rstrip("/")
        parts = urlsplit(value)
        if parts.scheme not in ("http", "https") or not parts.netloc:
            raise ValueError(
                "CTFD_BASE_URL must be an absolute http(s) URL, "
                f"e.g. https://ctf.example.com (got {value!r})"
            )
        if parts.query or parts.fragment:
            raise ValueError("CTFD_BASE_URL must not contain a query string or fragment")
        if "@" in parts.netloc:
            raise ValueError("CTFD_BASE_URL must not embed credentials")
        return value

    @field_validator("http_timeout")
    @classmethod
    def _validate_timeout(cls, value: float) -> float:
        if value <= 0:
            raise ValueError("CTFD_HTTP_TIMEOUT must be greater than zero")
        return value

    @field_validator("mcp_transport")
    @classmethod
    def _validate_transport(cls, value: str) -> str:
        value = value.strip().lower()
        if value not in ("stdio", "sse"):
            raise ValueError("CTFD_MCP_TRANSPORT must be 'stdio' or 'sse'")
        return value

    @property
    def base_url_is_set(self) -> bool:
        return bool(self.ctfd_base_url)


settings = Settings()