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

    # HTTP / transport settings.
    http_timeout: float = Field(default=15.0, validation_alias=AliasChoices("CTFD_HTTP_TIMEOUT", "http_timeout"))
    http_max_redirects: int = 5

    # MCP server settings (used when running on the "sse"/"http" transport).
    mcp_host: str = "0.0.0.0"
    mcp_port: int = 8000

    # Where downloaded challenge files are saved.
    file_cache_dir: str = "./file_cache"

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