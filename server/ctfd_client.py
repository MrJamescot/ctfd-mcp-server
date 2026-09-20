"""CTFd API client.

A single reusable client used by both the MCP tool layer and the optional
FastAPI REST interface.  It talks to a generic CTFd v3 instance through
``server.gateway.Gateway``; all network access funnels through this class so
authentication, pagination and error handling stay consistent.

Security notes:
  * credentials never appear in return values or raised errors,
  * flags are never logged,
  * flag submission requires an explicit ``confirm=True``,
  * write requests are never retried (prevents duplicate submissions).
"""

from __future__ import annotations

import logging
from typing import Any

from .errors import (
    AuthenticationError,
    ChallengeNotFoundError,
    ConfigurationError,
    CTFdAPIError,
    SubmissionError,
    ValidationError,
)
from .file_cache import save_file
from .gateway import gateway as default_gateway
from .session_manager import session_manager
from .state_manager import state
from .utils import extract_csrf_nonce, extract_version, safe_host, sanitize

logger = logging.getLogger("ctfd.client")

DEFAULT_PER_PAGE = 25
MAX_PER_PAGE = 100


class CTFdClient:
    """High-level, safe operations against a CTFd instance."""

    def __init__(self, gateway=None) -> None:
        self.gateway = gateway or default_gateway
        self._last_scan_pages = 0

    # ------------------------------------------------------------ auth

    async def set_token(self, token: str) -> dict[str, Any]:
        """Adopt an API token for subsequent requests (memory only)."""
        if not token or not str(token).strip():
            raise ValidationError("token must not be empty.")
        state.set_token(str(token).strip())
        return {"success": True, "auth_mode": state.auth_mode()}

    async def set_cookie(self, cookie: str) -> dict[str, Any]:
        """Adopt a session cookie for subsequent requests (memory only)."""
        if not cookie or not str(cookie).strip():
            raise ValidationError("cookie must not be empty.")
        state.set_cookie(str(cookie).strip())
        return {"success": True, "auth_mode": state.auth_mode()}

    async def login(self, username: str, password: str) -> dict[str, Any]:
        """Log in through the CTFd web form and keep the session cookie.

        Extraction of the CSRF nonce is best-effort; instances with CSRF
        disabled are handled too.  On success the session cookie is stored in
        memory and the client switches to cookie authentication.
        """
        if not username or not password:
            raise ValidationError("username and password are required.")

        base = self.gateway.base
        if not base:
            raise ConfigurationError(
                "CTFd base URL is not configured. Set CTFD_BASE_URL or call set_base_url."
            )

        nonce = await self._fetch_login_nonce()

        form: dict[str, str] = {"name": username, "password": password}
        if nonce:
            form["nonce"] = nonce

        try:
            res = await self.gateway.request(
                "POST",
                "/login",
                use_api=False,
                data=form,
                raw=True,
                retry=False,
                allow_redirects=False,
            )
        except CTFdAPIError as exc:
            raise CTFdAPIError(
                f"Could not reach the CTFd login page at {safe_host(base)}.",
                0,
            ) from exc

        status = res.get("status", 0)
        if status >= 400:
            raise AuthenticationError(
                f"CTFd rejected the login (HTTP {status}).",
                detail="Verify the username and password.",
            )

        set_cookies = res.get("set_cookie") or ""
        if not set_cookies and res.get("text"):
            # Some instances do not send Set-Cookie on the redirect; fall back
            # to collecting them from the response headers is handled above.
            pass

        if not set_cookies:
            # Instances that never set a cookie on the redirect response: probe
            # /users/me to confirm the credentials actually authenticated us.
            try:
                me = await self._get("/users/me")
                authed = bool((me or {}).get("data", {}).get("id"))
            except AuthenticationError:
                authed = False
            if not authed:
                raise AuthenticationError(
                    "Login did not produce a session and credentials were rejected.",
                )

        if set_cookies:
            state.set_cookie(set_cookies)
        state.set_creds(username, password)
        state.set_token("")  # wipe any stale token; use the fresh cookie

        return {
            "success": True,
            "mode": state.auth_mode(),
            "csrf_used": bool(nonce),
        }

    async def refresh_login(self) -> dict[str, Any]:
        """Re-run login with stored credentials (used after expired sessions)."""
        username = state.get_username()
        password = state.get_password()
        if not username or not password:
            raise AuthenticationError(
                "Cannot auto-login: no credentials stored.",
                detail="Call login(username, password) first.",
            )
        return await self.login(username, password)

    async def auth_status(self) -> dict[str, Any]:
        """Report the current authentication state without revealing secrets."""
        mode = state.auth_mode()
        configured = state.is_configured()

        if not configured:
            return {
                "authenticated": None,
                "configured": False,
                "auth_mode": mode,
                "username": None,
                "note": "No token/cookie/credentials configured.",
            }

        verified: bool | None
        try:
            me = await self._get("/users/me")
            verified = bool((me or {}).get("data", {}).get("id"))
        except AuthenticationError:
            verified = False
        except CTFdAPIError:
            verified = None  # reachable but weird; unknown validity

        return {
            "authenticated": verified,
            "configured": True,
            "auth_mode": mode,
            "username": state.get_username(),
            "note": None,
        }

    # ------------------------------------------------------- challenges

    async def list_challenges(
        self,
        category: str | None = None,
        search: str | None = None,
        solved: bool | None = None,
        page: int = 1,
        per_page: int = DEFAULT_PER_PAGE,
        max_pages: int = 10,
    ) -> dict[str, Any]:
        """Return a page of challenges, optionally filtered.

        Without filters this performs exactly one API call (proper
        pagination).  With filters, up to ``max_pages`` are scanned and the
        matching challenges are collected client-side.

        ``solved`` filters on the ``solved_by_me`` field that CTFd attaches to
        authenticated list responses.
        """
        if page < 1:
            raise ValidationError("page must be >= 1.")
        if not 1 <= per_page <= MAX_PER_PAGE:
            raise ValidationError(f"per_page must be between 1 and {MAX_PER_PAGE}.")
        if solved not in (None, True, False):
            raise ValidationError("solved must be True, False or None.")

        has_filters = bool(category) or bool(search) or solved is not None

        if not has_filters:
            payload = await self._get(
                "/challenges", params={"page": page, "per_page": per_page}
            )
            items = self._extract_challenges(payload)
            self._remember_challenges(items)
            return self._structure_page(items, payload, page, per_page)

        items = await self._scan_challenges(
            category or "", search or "", solved, per_page, max_pages
        )
        return {
            "items": [self._summarize(c) for c in items],
            "meta": {
                "page": 1,
                "per_page": per_page,
                "total_matches": len(items),
                "scanned_pages": self._last_scan_pages,
                "filtered": True,
            },
            "count": len(items),
        }

    async def get_challenge(self, identifier: int | str) -> dict[str, Any]:
        """Return the full detail of one challenge by numeric id or name."""
        try:
            if isinstance(identifier, str) and not identifier.isdigit():
                cid = await self._resolve_by_name(identifier)
            else:
                cid = int(identifier)

            if cid is None:
                raise ChallengeNotFoundError(f"Challenge {identifier!r} not found.")

            payload = await self._get(f"/challenges/{cid}")
        except CTFdAPIError as exc:
            if exc.status == 404:
                raise ChallengeNotFoundError(
                    f"Challenge {identifier!r} not found (or not visible)."
                ) from exc
            raise

        data = payload.get("data")
        if not data:
            raise ChallengeNotFoundError(
                f"Challenge {identifier!r} returned no detail."
            )
        return sanitize(data)

    # ------------------------------------------------------------- flags

    async def submit_flag(
        self,
        flag: str,
        challenge_id: int | None = None,
        challenge_name: str | None = None,
        confirm: bool = False,
    ) -> dict[str, Any]:
        """Submit a flag and report a clear success/failure result.

        Safety: requires ``confirm=True`` (an explicit opt-in from the caller)
        and never logs the flag value.
        """
        if not confirm:
            raise ValidationError(
                "Flag submission requires an explicit opt-in: pass confirm=True."
            )
        if not flag or not str(flag).strip():
            raise ValidationError("flag must not be empty.")
        if (challenge_id is None) == (challenge_name is None):
            raise ValidationError(
                "Provide exactly one of challenge_id or challenge_name."
            )

        cid: int | None
        if challenge_name:
            cid = await self._resolve_by_name(challenge_name)
        else:
            cid = int(challenge_id) if challenge_id is not None else None

        if cid is None:
            raise ChallengeNotFoundError(
                f"Could not resolve challenge for submission: "
                f"{challenge_name or challenge_id}."
            )

        payload = {"challenge_id": cid, "submission": str(flag).strip()}
        try:
            res = await self.gateway.request(
                "POST", "/challenges/attempt", json=payload, allow_failure=True
            )
        except CTFdAPIError as exc:
            if exc.status == 429:
                raise SubmissionError(
                    "CTFd rate-limited the flag submission (wait before retrying)."
                ) from exc
            raise SubmissionError(
                f"CTFd rejected the submission (HTTP {exc.status})."
            ) from exc
        except AuthenticationError as exc:
            raise AuthenticationError(
                "Not authenticated; set a token/cookie or log in first."
            ) from exc

        return self._parse_attempt(cid, res)

    # ------------------------------------------------------- instance info

    async def scoreboard(self) -> dict[str, Any]:
        """Return the public scoreboard (top standings)."""
        payload = await self._get("/scoreboard")
        return {"success": True, "data": sanitize(payload.get("data") or payload)}

    async def progress(self) -> dict[str, Any]:
        """Return the authenticated user's progress (score + solves)."""
        payload = await self._get("/users/me")
        data = payload.get("data") or {}
        solves = data.get("solves") or []
        return {
            "success": True,
            "data": {
                "name": data.get("name"),
                "score": data.get("score"),
                "solved_count": len(solves),
                "solves": [
                    {"id": s.get("id"), "name": s.get("name")} for s in solves
                ],
            },
        }

    async def instance_info(self) -> dict[str, Any]:
        """Public instance metadata.  Never includes secrets."""
        base = self.gateway.base
        if not base:
            raise ConfigurationError(
                "CTFd base URL is not configured. Set CTFD_BASE_URL or call set_base_url."
            )

        info: dict[str, Any] = {
            "base_url": safe_host(base),
            "reachable": False,
            "api_ok": False,
            "public_scoreboard": False,
            "auth_mode": state.auth_mode(),
            "configured": True,
            "detected_version": None,
            "notes": [],
        }

        try:
            payload = await self.gateway.request(
                "GET", "/scoreboard", allow_failure=True, retry=True
            )
            info["reachable"] = True
            info["api_ok"] = True
            if isinstance(payload, dict) and payload.get("success") is not False:
                info["public_scoreboard"] = True
        except CTFdAPIError as exc:
            info["reachable"] = exc.status != 0
            info["notes"].append(
                f"scoreboard probe failed (HTTP {exc.status or 'unreachable'})"
            )

        try:
            raw = await self.gateway.request(
                "GET", "/", use_api=False, raw=True, retry=True
            )
            if raw["text"]:
                version = extract_version(raw["text"])
                if version:
                    info["detected_version"] = version
        except CTFdAPIError:
            pass

        return info

    # ------------------------------------------------------------ health

    async def download_challenge_file(self, file_id: int, filename: str) -> dict[str, Any]:
        """Download a challenge file into the local cache directory.

        Returns the saved path.  Raises ``CTFdAPIError`` on failure.
        """
        base = self.gateway.base
        if not base:
            raise ConfigurationError(
                "CTFd base URL is not configured. Set CTFD_BASE_URL or call set_base_url."
            )
        url = f"{base.rstrip('/')}/api/v1/files/{file_id}/download"
        session = await session_manager.get_session()
        headers = dict(session_manager.auth_headers())
        async with session.get(url, headers=headers) as response:
            if response.status != 200:
                raise CTFdAPIError(
                    f"CTFd returned HTTP {response.status} for file {file_id}.",
                    response.status,
                )
            content = await response.read()
        path = save_file(filename or f"file_{file_id}", content)
        return {"success": True, "path": path, "file_id": file_id}

    async def health(self) -> dict[str, Any]:
        """Combine reachability, API and authentication checks."""
        base = self.gateway.base
        if not base:
            result = {
                "status": "error",
                "ctfd_reachable": False,
                "authenticated": None,
                "auth_mode": state.auth_mode(),
                "message": "CTFd base URL is not configured. Set CTFD_BASE_URL.",
            }
            state.set_last_health(result)
            return result

        result: dict[str, Any] = {
            "status": "degraded",
            "ctfd_reachable": False,
            "api_ok": False,
            "authenticated": None,
            "auth_mode": state.auth_mode(),
            "message": None,
        }

        try:
            payload = await self.gateway.request(
                "GET", "/challenges", allow_failure=True, retry=True
            )
            result["ctfd_reachable"] = True
            result["api_ok"] = isinstance(payload, dict)
        except AuthenticationError:
            if state.auth_mode() == "credentials":
                logger.info("Challenges probe unauthenticated; refreshing login automatically.")
                try:
                    await self.refresh_login()
                    payload = await self.gateway.request(
                        "GET", "/challenges", allow_failure=True, retry=True
                    )
                    result["ctfd_reachable"] = True
                    result["api_ok"] = isinstance(payload, dict)
                except (AuthenticationError, CTFdAPIError) as exc:
                    result["ctfd_reachable"] = (
                        exc.status != 0 if isinstance(exc, CTFdAPIError) else False
                    )
                    result["message"] = "challenges probe failed; login could not be refreshed."
            else:
                result["ctfd_reachable"] = True
                result["message"] = (
                    "challenges probe returned the login page: the credential is not "
                    "valid for this instance (or the account has no access)."
                )
        except CTFdAPIError as exc:
            result["ctfd_reachable"] = exc.status != 0
            result["message"] = f"challenges probe failed (HTTP {exc.status or 'unreachable'})"

        if state.is_configured():
            try:
                me = await self.gateway.request("GET", "/users/me", allow_failure=True)
                result["authenticated"] = bool((me or {}).get("data", {}).get("id"))
            except (AuthenticationError, CTFdAPIError):
                result["authenticated"] = False

        if result.get("authenticated") is not False or not state.is_configured():
            result["status"] = "ok" if result["ctfd_reachable"] else "error"

        state.set_last_health(result)
        return result

    # --------------------------------------------------------- internals

    async def _get(self, path: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        try:
            return await self.gateway.request("GET", path, params=params, retry=True)
        except AuthenticationError:
            if state.auth_mode() == "credentials":
                logger.info("Session expired; refreshing login automatically.")
                await self.refresh_login()
                return await self.gateway.request("GET", path, params=params, retry=True)
            raise

    async def _fetch_login_nonce(self) -> str | None:
        try:
            raw = await self.gateway.request(
                "GET", "/login", use_api=False, raw=True, retry=True
            )
        except CTFdAPIError:
            return None
        nonce = extract_csrf_nonce(raw.get("text") or "")
        session_manager.set_csrf_nonce(nonce)
        return nonce

    async def _resolve_by_name(self, name: str) -> int | None:
        cid = state.name_to_id(name)
        if cid is not None:
            return cid
        # Populate the name->id index by scanning recent challenges.
        await self._scan_challenges("", name, None, DEFAULT_PER_PAGE * 2, 10)
        return state.name_to_id(name)

    async def _scan_challenges(
        self,
        category: str,
        search: str,
        solved: bool | None,
        per_page: int,
        max_pages: int,
    ) -> list[dict[str, Any]]:
        matches: list[dict[str, Any]] = []
        self._last_scan_pages = 0
        for page in range(1, max_pages + 1):
            payload = await self._get(
                "/challenges", params={"page": page, "per_page": per_page}
            )
            items = self._extract_challenges(payload)
            self._last_scan_pages = page
            for item in items:
                self._remember_challenges([item])
                if category and item.get("category") != category:
                    continue
                if search and search.lower() not in str(item.get("name", "")).lower():
                    continue
                if solved is not None and bool(item.get("solved_by_me")) is not solved:
                    continue
                matches.append(item)
            if not items:
                break
        return matches

    @staticmethod
    def _extract_challenges(payload: Any) -> list[dict[str, Any]]:
        data = payload.get("data") if isinstance(payload, dict) else None
        return data if isinstance(data, list) else []

    def _remember_challenges(self, items: list[dict[str, Any]]) -> None:
        for item in items:
            name = item.get("name")
            cid = item.get("id")
            if name and isinstance(cid, int):
                state.update_challenge(str(name), cid)

    def _structure_page(
        self, items: list[dict[str, Any]], payload: dict[str, Any], page: int, per_page: int
    ) -> dict[str, Any]:
        meta = payload.get("meta", {})
        pagination = meta.get("pagination") or {}
        total = pagination.get("count") if pagination else None
        if total is None and isinstance(payload.get("data"), list):
            total = len(items)
        return {
            "items": [self._summarize(c) for c in items],
            "meta": {
                "page": page,
                "per_page": per_page,
                "total": total,
                "has_more": bool(pagination.get("next")) if pagination else False,
            },
            "count": len(items),
        }

    @staticmethod
    def _summarize(challenge: dict[str, Any]) -> dict[str, Any]:
        """Compact per-challenge summary for AI agents."""
        return {
            "id": challenge.get("id"),
            "name": challenge.get("name"),
            "category": challenge.get("category"),
            "value": challenge.get("value"),
            "solved_by_me": challenge.get("solved_by_me", False),
            "solves": challenge.get("solves"),
            "type": challenge.get("type"),
        }

    @staticmethod
    def _parse_attempt(cid: int, res: Any) -> dict[str, Any]:
        data = res.get("data") if isinstance(res, dict) else {}
        if not isinstance(data, dict):
            data = {}
        status = data.get("status")
        message = data.get("message")
        if not isinstance(res, dict) or res.get("success") is False:
            errors = res.get("errors") if isinstance(res, dict) else None
            text = errors[0] if isinstance(errors, list) and errors else "unknown"
            return {
                "success": False,
                "challenge_id": cid,
                "status": None,
                "message": str(text),
            }
        if status == "correct":
            return {
                "success": True,
                "challenge_id": cid,
                "status": "correct",
                "message": message or "Flag accepted.",
                "points_earned": data.get("points_earned"),
            }
        return {
            "success": False,
            "challenge_id": cid,
            "status": status or "incorrect",
            "message": message or "Flag was not accepted.",
        }


ctfd_client = CTFdClient()