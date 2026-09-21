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
from .utils import api_base, is_private_or_metadata_url, is_valid_http_url, safe_host

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
        if not settings.ctfd_allow_private_ips and is_private_or_metadata_url(url):
            raise ConfigurationError(
                "CTFd URL targets a private/loopback/link-local address or a "
                "metadata endpoint, which is blocked by default. Set "
                "CTFD_ALLOW_PRIVATE_IPS=1 to permit a local CTFd instance.",
            )
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
        if not settings.ctfd_allow_private_ips and is_private_or_metadata_url(base):
            raise ConfigurationError(
                "CTFd base URL targets a private/loopback/link-local address or a "
                "metadata endpoint, which is blocked by default. Set "
                "CTFD_ALLOW_PRIVATE_IPS=1 to permit a local CTFd instance.",
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
        if use_api and state.get_token() and "Content-Type" not in request_headers:
            # CTFd only honours "Authorization: Token ..." when the request
            # body is JSON (request.is_json); without this header token auth is
            # silently ignored and the request is treated as anonymous.
            request_headers["Content-Type"] = "application/json"
        if (
            use_api
            and method.upper() not in ("GET", "HEAD", "OPTIONS", "TRACE")
            and state.auth_mode() in ("cookie", "credentials")
        ):
            # CTFd v3 CSRF: JSON state-changing requests over a web session
            # must echo the session nonce as the CSRF-Token header.
            request_headers.update(session_manager.csrf_headers())

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
                    max_redirects=settings.http_max_redirects,
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
                    return await self._decode(method, path, response, allow_failure, use_api=use_api)
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
                      allow_failure: bool, use_api: bool = True) -> Any:
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
            and use_api
            and ("html" in content_type.lower() or "<html" in body_text[:200].lower())
        ):
            # CTFd's /api/v1* routes return JSON.  An HTML body here means the
            # request was bounced to a login/landing page (some deployments,
            # e.g. behind a reverse proxy, respond 200 instead of 302).
            raise AuthenticationError(
                f"CTFd returned an HTML page instead of JSON for the API "
                f"({method} {path}). This usually means the request was "
                "unauthenticated and bounced to a login page, or the base URL "
                "does not point at a CTFd instance.",
                detail=(
                    "Provide a valid credential for this CTFd instance, check "
                    "CTFD_BASE_URL, or log in first in credentials mode."
                ),
            )

        if response.status == 401:
            raise AuthenticationError(
                "CTFd rejected the request (401 UNAUTHORIZED).",
                detail="Check the token/cookie or log in first.",
            )

        if response.status == 403:
            raise AuthenticationError(
                "CTFd rejected the request (403 FORBIDDEN).",
                detail=(
                    "The credential may be invalid, the account lacks permission "
                    "(e.g. not in a team, or the endpoint requires admin), or a "
                    "state-changing request with a session cookie was missing its "
                    "CSRF-Token. Re-login or join/create a team, then retry."
                ),
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