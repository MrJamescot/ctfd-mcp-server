"""Runtime state for the server.

Credentials (token / cookie / password) live in memory only.  By default they
are never written to ``server_state.json`` (set ``CTFD_PERSIST_SECRETS=1`` to
opt into persisting them, which is strongly discouraged).  Non-secret caches
(the challenge id/name map, the last health result and the configured base
URL) are persisted so they survive restarts.

The persisted ``challenge_map`` is ``{name: id}`` and is stored as plain text;
it contains no credentials.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .config import settings
from .utils import mask

STATE_FILE = Path("./server_state.json")


class StateManager:
    def __init__(self) -> None:
        self._token: str | None = None
        self._cookie: str | None = None
        self._username: str | None = None
        self._password: str | None = None

        self._challenge_map: dict[str, int] = {}
        self._last_health: dict[str, Any] | None = None
        self._base_url: str | None = None

        self._load()

    # ------------------------------------------------------------------ load

    def _load(self) -> None:
        try:
            raw = json.loads(STATE_FILE.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return

        self._challenge_map = dict(raw.get("challenge_map") or {})
        self._last_health = raw.get("last_health")
        self._base_url = raw.get("base_url")

        if settings.persist_secrets:
            self._token = raw.get("token") or None
            self._cookie = raw.get("cookie") or None
            self._password = raw.get("password") or None
            self._username = raw.get("username") or None

    # ----------------------------------------------------------------- save

    def _save(self) -> None:
        """Persist non-secret state.  Secrets are only written when enabled."""
        payload: dict[str, Any] = {
            "challenge_map": self._challenge_map,
            "last_health": self._last_health,
            "base_url": self._base_url,
        }
        if settings.persist_secrets:
            payload.update(
                {
                    "token": self._token,
                    "cookie": self._cookie,
                    "username": self._username,
                    "password": self._password,
                }
            )
        try:
            STATE_FILE.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        except OSError:
            # State persistence is best-effort; the process keeps running.
            pass

    # -------------------------------------------------------------- secrets

    def set_token(self, token: str) -> None:
        self._token = token if token else None
        self._save()

    def set_cookie(self, cookie: str) -> None:
        self._cookie = cookie if cookie else None
        self._save()

    def set_creds(self, username: str, password: str) -> None:
        self._username = username if username else None
        self._password = password if password else None
        self._save()

    def set_base_url(self, url: str) -> None:
        self._base_url = url
        self._save()

    # ------------------------------------------------------------- queries

    def get_token(self) -> str | None:
        return self._token

    def get_cookie(self) -> str | None:
        return self._cookie

    def get_username(self) -> str | None:
        return self._username

    def get_password(self) -> str | None:
        return self._password

    def get_base_url(self) -> str | None:
        return self._base_url

    def get_last_health(self) -> dict[str, Any] | None:
        return self._last_health

    def auth_mode(self) -> str:
        """Active authentication mode (precedence: token > cookie > creds)."""
        if self._token:
            return "token"
        if self._cookie:
            return "cookie"
        if self._username and self._password:
            return "credentials"
        return "none"

    def is_configured(self) -> bool:
        return self.auth_mode() != "none"

    # -------------------------------------------------------------- caching

    def update_challenge(self, name: str, challenge_id: int) -> None:
        """Remember ``name -> id`` so flags can be submitted by name too."""
        self._challenge_map[name] = challenge_id
        self._save()

    def name_to_id(self, name: str) -> int | None:
        return self._challenge_map.get(name)

    def id_to_name(self, challenge_id: int) -> str | None:
        for name, cid in self._challenge_map.items():
            if cid == challenge_id:
                return name
        return None

    def known_challenge_names(self):
        return list(self._challenge_map.keys())

    def challenge_count(self) -> int:
        return len(self._challenge_map)

    def set_last_health(self, obj: dict[str, Any]) -> None:
        self._last_health = obj
        self._save()

    # ------------------------------------------------------------ reporting

    def public_snapshot(self) -> dict[str, Any]:
        """Safe snapshot for logs/output.  Never includes secrets in clear."""
        return {
            "auth_mode": self.auth_mode(),
            "token_masked": mask(self._token),
            "username": self._username,
            "base_url": self._base_url,
            "known_challenges": len(self._challenge_map),
        }


state = StateManager()