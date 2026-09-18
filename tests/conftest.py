"""Shared test fixtures: a fake gateway that never touches the network."""

from __future__ import annotations

import json

import pytest

from server import state_manager


class FakeGateway:
    """Drop-in replacement for server.gateway.Gateway.

    Returns canned responses keyed by (METHOD, PATH).  ``raise_on`` lets tests
    simulate transport failures.  ``base`` is a fixed, safe URL.
    """

    def __init__(self, base: str = "https://ctf.example.com"):
        self.base = base
        self.responses = {}
        self.raise_exc = None
        self.calls = []

    def set_base(self, url: str) -> str:
        self.base = url.rstrip("/")
        return self.base

    async def request(self, method, path, **kwargs):
        self.calls.append((method, path, kwargs))
        if self.raise_exc:
            exc = self.raise_exc
            self.raise_exc = None
            raise exc
        key = (method.upper(), path)
        value = self.responses.get(key)
        if value is None:
            raise AssertionError(f"Unexpected request: {method} {path}")
        if callable(value):
            return value(method, path, kwargs)
        return value

    def json_response(self, method: str, path: str, payload: dict):
        """Register a JSON response, honoring the raw/JSON error paths."""
        self.responses[(method.upper(), path)] = payload


def make_challenge(cid: int, name: str, category: str = "web", value: int = 100,
                   solved: bool = False) -> dict:
    return {
        "id": cid,
        "name": name,
        "category": category,
        "value": value,
        "solved_by_me": solved,
        "solves": 5,
        "type": "standard",
    }


def challenge_page(items: list, count: int | None = None, page: int = 1,
                   per_page: int = 25) -> dict:
    total = count if count is not None else len(items)
    pages = max(1, -(-total // per_page))
    return {
        "success": True,
        "data": items,
        "meta": {
            "pagination": {
                "page": page,
                "per_page": per_page,
                "count": total,
                "pages": pages,
                "next": page + 1 if page * per_page < total else None,
                "previous": page - 1 if page > 1 else None,
            }
        },
    }


@pytest.fixture(autouse=True)
def isolated_state(tmp_path, monkeypatch):
    """Point the state file at a temp location and reset in-memory state."""
    monkeypatch.setattr(state_manager, "STATE_FILE", tmp_path / "state.json")
    state = state_manager.state
    state._token = None
    state._cookie = None
    state._username = None
    state._password = None
    state._challenge_map = {}
    state._last_health = None
    state._base_url = None
    return state


@pytest.fixture
def fake_gateway():
    return FakeGateway()


@pytest.fixture
def client(fake_gateway):
    from server.ctfd_client import CTFdClient

    return CTFdClient(gateway=fake_gateway)


def raises(exception_type):
    return pytest.raises(exception_type)


def safe_json(payload):
    return json.dumps(payload, default=str)