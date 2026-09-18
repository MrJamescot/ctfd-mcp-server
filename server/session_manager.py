"""Owns the shared aiohttp session and translates state into HTTP headers.

Precedence: an explicit token is preferred over a session cookie, which is
preferred over form-login credentials.  The session reuses a single
``aiohttp.ClientSession`` with a cookie jar so form-login cookies are kept
automatically; no secret is ever logged here.
"""

from __future__ import annotations

import aiohttp

from .config import settings
from .state_manager import state

DEFAULT_HEADERS = {
    "User-Agent": "ctfd-mcp-server/1.0 (+https://github.com/MrJamescot/ctfd-mcp-server)",
    "Accept-Encoding": "gzip, deflate",
}


class SessionManager:
    def __init__(self) -> None:
        self.session: aiohttp.ClientSession | None = None
        self.csrf_nonce: str | None = None

    def auth_headers(self) -> dict[str, str]:
        """Build the ``Authorization``/``Cookie`` header from current state.

        Returns an empty dict when no credentials are configured, which lets
        public CTFd endpoints be reached anonymously.
        """
        headers: dict[str, str] = {}
        if state.get_token():
            headers["Authorization"] = f"Token {state.get_token()}"
        elif state.get_cookie():
            headers["Cookie"] = state.get_cookie()
        return headers

    def cookie_jar(self) -> aiohttp.CookieJar:
        # ``unsafe=True`` is required so HTTP (non-TLS) CTFd instances used in
        # local development can still store session cookies.
        return aiohttp.CookieJar(unsafe=True)

    async def get_session(self) -> aiohttp.ClientSession:
        if self.session is None or self.session.closed:
            timeout = aiohttp.ClientTimeout(
                total=settings.http_timeout,
                connect=min(settings.http_timeout, 5.0),
                sock_read=settings.http_timeout,
            )
            self.session = aiohttp.ClientSession(
                headers=dict(DEFAULT_HEADERS),
                timeout=timeout,
                cookie_jar=self.cookie_jar(),
                connector=aiohttp.TCPConnector(limit=10, limit_per_host=5),
            )
        return self.session

    async def refresh_headers(self) -> None:
        """Re-apply auth headers to an existing (open) session."""
        if not self.session:
            return
        # aiohttp applies headers from the session for each request, so simply
        # syncing what the session currently carries is not enough: we remove
        # stale keys first by building a clean per-request header later in the
        # gateway.  Here we only update the base headers.
        self.session._default_headers.update(self.auth_headers())  # type: ignore[union-attr]

    def set_csrf_nonce(self, nonce: str | None) -> None:
        self.csrf_nonce = nonce

    async def close(self) -> None:
        if self.session and not self.session.closed:
            await self.session.close()
        self.session = None


session_manager = SessionManager()