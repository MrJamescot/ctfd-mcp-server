"""HTTP layer between the server and a CTFd instance.

Responsibilities:
  * build ``<base>/api/v1/<path>`` URLs (and raw non-API URLs for login),
  * apply the active authentication headers (token / cookie),
  * enforce timeouts and a single safe retry for idempotent GETs only,
  * decode JSON responses and raise structured errors on failures,
  * never echo credentials or request bodies into exceptions/logs.
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import logging
from typing import Any

import aiohttp

from .config import settings
from .errors import (
    AuthenticationError,
    ConfigurationError,
    CTFdAPIError,
    ServerDownError,
)
from .session_manager import session_manager
from .state_manager import state
from .utils import api_base, is_valid_http_url, safe_host

logger = logging.getLogger("ctfd.gateway")


class Gateway:
    def __init__(self) -> None:
        self._base: str | None = None

    # ------------------------------------------------------------ base URL

    @property
    def base(self) -> str:
        """Effective base URL: runtime override first, then settings."""
        if self._base:
            return self._base
        if state.get_base_url():
            return state.get_base_url()  # type: ignore[return-value]
        return settings.ctfd_base_url

    def set_base(self, url: str) -> str:
        """Validate and set the CTFd base URL (runtime override)."""
        if not is_valid_http_url(url):
            raise ConfigurationError(f"Invalid CTFd URL: {url!r}")
        self._base = url.rstrip("/")
        state.set_base_url(self._base)
        return self._base

    # ------------------------------------------------------------- requests

    async def request(
        self,
        method: str,
        path: str,
        *,
        json: dict[str, Any] | None = None,
        data: dict[str, Any] | None = None,
        params: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
        use_api: bool = True,
        allow_failure: bool = False,
        retry: bool = False,
        raw: bool = False,
        allow_redirects: bool = True,
    ) -> Any:
        """Perform an HTTP request and return the parsed JSON body.

        Unless ``raw=True``, raises ``ConfigurationError`` when no CTFd URL is
        configured, ``AuthenticationError`` for 401/403, ``CTFdAPIError`` for
        transport / non-JSON / 4xx-5xx failures (unless ``allow_failure``),
        and ``ServerDownError`` for 5xx responses.

        ``allow_failure`` returns the parsed body even when CTFd reports
        ``"success": false`` (used for flag attempts, whose ``status`` field
        is a normal, expected outcome).

        ``raw=True`` returns ``{"status", "text", "content_type",
        "set_cookie"}`` and skips all JSON/error interpretation (used for the
        HTML login page).
        """
        base = self.base
        if not base:
            raise ConfigurationError(
                "CTFd base URL is not configured. Set CTFD_BASE_URL or call set_base_url."
            )

        if use_api:
            url = f"{api_base(base)}{path}"
        else:
            url = f"{base.rstrip('/')}{path}"

        session = await session_manager.get_session()
        request_headers: dict[str, str] = {
            **session_manager.auth_headers(),
            **(headers or {}),
        }

        error: Exception | None = None
        attempts = 2 if (retry and method.upper() == "GET") else 1
        for attempt in range(attempts):
            try:
                async with session.request(
                    method,
                    url,
                    params=params,
                    headers=request_headers,
                    json=json,
                    data=data,
                    allow_redirects=allow_redirects,
                ) as response:
                    if raw:
                        return {
                            "status": response.status,
                            "text": await response.text(),
                            "content_type": response.headers.get("Content-Type", ""),
                            "set_cookie": "; ".join(
                                response.headers.getall("Set-Cookie", [])
                            ),
                        }
                    return await self._decode(method, path, response, allow_failure)
            except aiohttp.ClientConnectionError as exc:
                error = exc
            except asyncio.TimeoutError as exc:
                error = exc
            if error is not None and attempt + 1 < attempts:
                await asyncio.sleep(0.4)

        host = safe_host(base)
        raise CTFdAPIError(
            f"Could not reach CTFd at {host}: {type(error).__name__}",
            0,
            detail="Check connectivity and the CTFD_BASE_URL configuration.",
        )

    async def _decode(self, method: str, path: str, response: aiohttp.ClientResponse,
                      allow_failure: bool) -> Any:
        body_text = await response.text()
        content_type = response.headers.get("Content-Type", "")

        payload: Any = None
        if body_text and "json" in content_type.lower():
            with contextlib.suppress(json.JSONDecodeError):
                payload = json.loads(body_text)
        if payload is None and body_text:
            # Some CTFd deployments serve JSON without a proper content type.
            with contextlib.suppress(json.JSONDecodeError):
                payload = json.loads(body_text)

        if (
            payload is None
            and "html" in content_type.lower()
            and self._looks_like_login_page(body_text)
        ):
            raise AuthenticationError(
                    "CTFd redirected to its login page instead of returning JSON "
                    f"({method} {path}). The credential is not valid for THIS "
                    "instance (or the account has no access).",
                    detail=(
                        "Provide a valid API token/cookie for this CTFd instance, "
                        "or call set_cookie/login with the account of this instance."
                    ),
                )

        if response.status in (401, 403):
            raise AuthenticationError(
                f"CTFd rejected the request ({response.status} UNAUTHORIZED/FORBIDDEN).",
                detail="Check the token/cookie or log in first.",
            )

        if response.status == 429:
            raise CTFdAPIError(
                "CTFd rate-limited the request (429 Too Many Requests).",
                response.status,
            )

        if response.status >= 500:
            raise ServerDownError(
                f"CTFd server error (HTTP {response.status}).", response.status
            )

        if payload is None:
            raise CTFdAPIError(
                f"CTFd returned a non-JSON response (HTTP {response.status}).",
                response.status,
                detail=f"content-type={content_type or 'unknown'} (body omitted)",
            )

        if response.status == 404:
            raise CTFdAPIError(
                f"CTFd returned 404 for {method} {path}.", response.status
            )

        if isinstance(payload, dict) and payload.get("success") is False and not allow_failure:
            errors = payload.get("errors") or ["unknown CTFd error"]
            if isinstance(errors, list):
                message = "; ".join(str(e) for e in errors[:3])
            else:
                message = str(errors)
            raise CTFdAPIError(message or "CTFd API error", response.status)

        return payload

    @staticmethod
    def _looks_like_login_page(body_text: str) -> bool:
        """Best-effort detection that HTML came from an auth login page."""
        sample = body_text[:4000].lower()
        return (
            "/login" in sample
            or ">login<" in sample
            or "sign in" in sample
            or "log in" in sample
        )

    async def close(self) -> None:
        await session_manager.close()


gateway = Gateway()