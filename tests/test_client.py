"""Client behaviour tests using a mocked CTFd API (no network)."""

from __future__ import annotations

import json
import unittest

from server import state_manager
from server.ctfd_client import CTFdClient
from server.errors import (
    AuthenticationError,
    ChallengeNotFoundError,
    ConfigurationError,
    CTFdAPIError,
    SubmissionError,
    ValidationError,
)
from server.state_manager import state

from .conftest import challenge_page, make_challenge


class AlwaysRaisingGateway:
    """Gateway that always raises the configured exception."""

    def __init__(self, exc):
        self.exc = exc
        self.base = "https://ctf.example.com"

    def set_base(self, url):
        self.base = url
        return url

    async def request(self, method, path, **kwargs):
        raise self.exc


def build_client(gateway):
    return CTFdClient(gateway=gateway)


class AuthTests(unittest.IsolatedAsyncioTestCase):
    async def test_set_token_switches_mode(self):
        from .conftest import FakeGateway

        c = build_client(FakeGateway())
        result = await c.set_token("ctfd_valid_token_123")
        self.assertTrue(result["success"])
        self.assertEqual(state.auth_mode(), "token")

    async def test_auth_status_unconfigured(self):
        from .conftest import FakeGateway

        c = build_client(FakeGateway())
        status = await c.auth_status()
        self.assertIsNone(status["authenticated"])
        self.assertFalse(status["configured"])

    async def test_auth_status_authenticated(self):
        from .conftest import FakeGateway

        gw = FakeGateway()
        gw.responses[("GET", "/users/me")] = {
            "success": True,
            "data": {"id": 7, "name": "bob", "score": 100},
        }
        c = build_client(gw)
        await c.set_token("tok")
        status = await c.auth_status()
        self.assertTrue(status["authenticated"])
        self.assertEqual(status["username"], None)  # token mode has no username

    async def test_auth_status_rejected_token(self):
        from .conftest import FakeGateway

        gw = FakeGateway()
        gw.raise_exc = AuthenticationError("CTFd rejected the request (401).")
        c = build_client(gw)
        await c.set_token("bad_token")
        status = await c.auth_status()
        self.assertFalse(status["authenticated"])

    async def test_login_success_stores_cookie(self):
        from .conftest import FakeGateway

        gw = FakeGateway()
        login_html = "<script>window.init = {'csrfNonce': 'feedbeefcafe'}</script>"
        gw.responses[("GET", "/login")] = {
            "status": 200,
            "text": login_html,
            "content_type": "text/html",
            "set_cookie": "",
        }
        gw.responses[("POST", "/login")] = {
            "status": 302,
            "text": "",
            "content_type": "text/html",
            "set_cookie": "session=cafe1234; Path=/; HttpOnly",
        }
        c = build_client(gw)
        result = await c.login("alice", "s3cret")
        self.assertTrue(result["success"])
        self.assertEqual(result["mode"], "cookie")
        self.assertTrue(result["csrf_used"])
        self.assertEqual(state.get_cookie(), "session=cafe1234; Path=/; HttpOnly")
        # The posted form carried the CSRF nonce
        post_kwargs = gw.calls[-1][2]
        self.assertEqual(post_kwargs["data"]["nonce"], "feedbeefcafe")

    async def test_login_rejected(self):
        from .conftest import FakeGateway

        gw = FakeGateway()
        gw.responses[("GET", "/login")] = {
            "status": 200, "text": "", "content_type": "text/html", "set_cookie": "",
        }
        gw.responses[("POST", "/login")] = {
            "status": 401, "text": "", "content_type": "text/html", "set_cookie": "",
        }
        c = build_client(gw)
        with self.assertRaises(AuthenticationError):
            await c.login("alice", "wrong")

    async def test_login_validation(self):
        from .conftest import FakeGateway

        c = build_client(FakeGateway())
        with self.assertRaises(ValidationError):
            await c.login("", "")


class ChallengeTests(unittest.IsolatedAsyncioTestCase):
    async def test_list_challenges_paginated(self):
        from .conftest import FakeGateway

        gw = FakeGateway()
        items = [
            make_challenge(1, "warmup", "misc", 50),
            make_challenge(2, "web1", "web", 100),
        ]
        gw.responses[("GET", "/challenges")] = challenge_page(items, count=60, page=1, per_page=25)
        c = build_client(gw)
        result = await c.list_challenges(page=1, per_page=25)
        self.assertEqual(result["count"], 2)
        self.assertEqual(result["meta"]["total"], 60)
        self.assertTrue(result["meta"]["has_more"])
        self.assertEqual(result["items"][0]["name"], "warmup")

    async def test_list_challenges_empty(self):
        from .conftest import FakeGateway

        gw = FakeGateway()
        gw.responses[("GET", "/challenges")] = challenge_page([], count=0)
        c = build_client(gw)
        result = await c.list_challenges()
        self.assertEqual(result["count"], 0)
        self.assertEqual(result["meta"]["total"], 0)

    async def test_filter_by_category_and_solved(self):
        from .conftest import FakeGateway

        gw = FakeGateway()
        page1 = [
            make_challenge(1, "sql", "web", solved=False),
            make_challenge(2, "rev", "reverse", solved=True),
        ]

        def page_resolver(method, path, kwargs):
            page = (kwargs.get("params") or {}).get("page", 1)
            if page <= 1:
                return {"success": True, "data": page1, "meta": {"pagination": {"count": 3}}}
            return {"success": True, "data": [], "meta": {"pagination": {"count": 3}}}

        gw.responses[("GET", "/challenges")] = page_resolver
        c = build_client(gw)
        result = await c.list_challenges(category="web", solved=False, per_page=25)
        self.assertEqual(len(result["items"]), 1)
        self.assertEqual(result["items"][0]["name"], "sql")

    async def test_search_by_name(self):
        from .conftest import FakeGateway

        gw = FakeGateway()
        page1 = [
            make_challenge(1, "SQL Injection I", "web"),
            make_challenge(2, "XSS Playground", "web"),
        ]

        def page_resolver(method, path, kwargs):
            page = (kwargs.get("params") or {}).get("page", 1)
            if page <= 1:
                return {"success": True, "data": page1, "meta": {"pagination": {"count": 2}}}
            return {"success": True, "data": [], "meta": {"pagination": {"count": 2}}}

        gw.responses[("GET", "/challenges")] = page_resolver
        c = build_client(gw)
        result = await c.list_challenges(search="xss", per_page=25)
        self.assertEqual([i["name"] for i in result["items"]], ["XSS Playground"])

    async def test_get_challenge_by_id(self):
        from .conftest import FakeGateway

        gw = FakeGateway()
        gw.responses[("GET", "/challenges/3")] = {
            "success": True,
            "data": {
                "id": 3, "name": "crypto one", "category": "crypto", "value": 200,
                "description": "solve it", "files": [], "hints": [],
            },
        }
        c = build_client(gw)
        detail = await c.get_challenge("3")
        self.assertEqual(detail["name"], "crypto one")
        self.assertEqual(detail["value"], 200)

    async def test_get_challenge_by_name_populates_map(self):
        from .conftest import FakeGateway

        gw = FakeGateway()
        gw.responses[("GET", "/challenges")] = challenge_page(
            [make_challenge(5, "botnets", "forensics", 300)], count=1
        )
        gw.responses[("GET", "/challenges/5")] = {
            "success": True,
            "data": {"id": 5, "name": "botnets", "category": "forensics"},
        }
        c = build_client(gw)
        detail = await c.get_challenge("botnets")
        self.assertEqual(detail["id"], 5)

    async def test_invalid_challenge_id_raises_not_found(self):
        from .conftest import FakeGateway

        gw = FakeGateway()
        gw.raise_exc = CTFdAPIError("CTFd returned 404 for GET /challenges/99999.", 404)
        c = build_client(gw)
        with self.assertRaises(ChallengeNotFoundError):
            await c.get_challenge("99999")

    async def test_get_challenge_bad_api_type(self):
        from .conftest import FakeGateway

        gw = FakeGateway()
        gw.raise_exc = CTFdAPIError("CTFd returned 404 for GET /challenges/abc.", 404)
        c = build_client(gw)
        with self.assertRaises(ChallengeNotFoundError):
            await c.get_challenge("does-not-exist")


class SubmissionTests(unittest.IsolatedAsyncioTestCase):
    async def test_submit_requires_confirm(self):
        from .conftest import FakeGateway

        c = build_client(FakeGateway())
        with self.assertRaises(ValidationError):
            await c.submit_flag(flag="flag{x}", challenge_id=1, confirm=False)

    async def test_submit_requires_one_target(self):
        from .conftest import FakeGateway

        c = build_client(FakeGateway())
        with self.assertRaises(ValidationError):
            await c.submit_flag(flag="flag{x}", confirm=True)

    async def test_submit_success(self):
        from .conftest import FakeGateway

        gw = FakeGateway()
        gw.responses[("POST", "/challenges/attempt")] = {
            "success": True,
            "data": {"status": "correct", "message": "Correct", "points_earned": 100},
        }
        c = build_client(gw)
        result = await c.submit_flag(flag="flag{real}", challenge_id=1, confirm=True)
        self.assertTrue(result["success"])
        self.assertEqual(result["status"], "correct")
        self.assertEqual(result["points_earned"], 100)

    async def test_submit_incorrect_flag_is_not_an_error(self):
        from .conftest import FakeGateway

        gw = FakeGateway()
        gw.responses[("POST", "/challenges/attempt")] = {
            "success": True,
            "data": {"status": "incorrect", "message": "That is not the flag"},
        }
        c = build_client(gw)
        result = await c.submit_flag(flag="flag{wrong}", challenge_id=1, confirm=True)
        self.assertFalse(result["success"])
        self.assertEqual(result["message"], "That is not the flag")

    async def test_submit_rejected_with_success_false(self):
        from .conftest import FakeGateway

        gw = FakeGateway()
        gw.responses[("POST", "/challenges/attempt")] = {
            "success": False,
            "errors": ["Slow down - you are submitting too fast"],
        }
        c = build_client(gw)
        result = await c.submit_flag(flag="flag{fast}", challenge_id=1, confirm=True)
        self.assertFalse(result["success"])

    async def test_submit_rate_limited_429(self):
        from .conftest import FakeGateway

        gw = FakeGateway()
        gw.raise_exc = CTFdAPIError("CTFd rate-limited the request (429).", 429)
        c = build_client(gw)
        with self.assertRaises(SubmissionError):
            await c.submit_flag(flag="flag{x}", challenge_id=1, confirm=True)

    async def test_submit_with_name_resolution(self):
        from .conftest import FakeGateway

        gw = FakeGateway()
        # pre-populate the map so no listing is required
        state.update_challenge("crypto one", 3)
        gw.responses[("POST", "/challenges/attempt")] = {
            "success": True,
            "data": {"status": "correct", "message": "Correct", "points_earned": 200},
        }
        c = build_client(gw)
        result = await c.submit_flag(flag="flag{ok}", challenge_name="crypto one", confirm=True)
        self.assertTrue(result["success"])
        posted = gw.calls[-1][2]["json"]
        self.assertEqual(posted, {"challenge_id": 3, "submission": "flag{ok}"})


class FailureTests(unittest.IsolatedAsyncioTestCase):
    async def test_timeout_raises_api_error_status_zero(self):
        c = build_client(AlwaysRaisingGateway(CTFdAPIError("Could not reach CTFd at x: TimeoutError", 0)))
        with self.assertRaises(CTFdAPIError) as ctx:
            await c.list_challenges()
        self.assertEqual(ctx.exception.status, 0)

    async def test_connection_error_maps_to_api_error(self):
        c = build_client(AlwaysRaisingGateway(CTFdAPIError("Could not reach CTFd at x: ClientConnectorError", 0)))
        with self.assertRaises(CTFdAPIError):
            await c.scoreboard()

    async def test_no_base_url_configuration_error(self):
        class NoBaseGateway:
            base = ""

            async def request(self, *a, **k):
                raise ConfigurationError(
                    "CTFd base URL is not configured. Set CTFD_BASE_URL or call set_base_url."
                )

        c = build_client(NoBaseGateway())
        with self.assertRaises(ConfigurationError) as ctx:
            await c.list_challenges()
        self.assertIn("CTFd base URL is not configured", str(ctx.exception))

    async def test_authentication_expired_does_not_retry_post(self):
        from .conftest import FakeGateway

        gw = FakeGateway()
        gw.raise_exc = AuthenticationError("CTFd rejected the request (401).")
        c = build_client(gw)
        with self.assertRaises(AuthenticationError):
            await c.progress()  # GET /users/me, no credential mode → re-raise
        self.assertEqual(len([c_ for c_ in gw.calls]), 1)


class StatusTests(unittest.IsolatedAsyncioTestCase):
    async def test_scoreboard(self):
        from .conftest import FakeGateway

        gw = FakeGateway()
        gw.responses[("GET", "/scoreboard")] = {
            "success": True,
            "data": {"standings": [{"rank": 1, "name": "team1", "score": 500}]},
        }
        c = build_client(gw)
        result = await c.scoreboard()
        self.assertEqual(result["data"]["standings"][0]["name"], "team1")

    async def test_progress_requires_auth(self):
        from .conftest import FakeGateway

        gw = FakeGateway()
        gw.raise_exc = AuthenticationError("CTFd rejected the request (401).")
        c = build_client(gw)
        with self.assertRaises(AuthenticationError):
            await c.progress()

    async def test_progress_success(self):
        from .conftest import FakeGateway

        gw = FakeGateway()
        gw.responses[("GET", "/users/me")] = {
            "success": True,
            "data": {
                "id": 1, "name": "bob", "score": 900,
                "solves": [{"id": 10, "name": "warmup"}, {"id": 11, "name": "cool"}],
            },
        }
        c = build_client(gw)
        result = await c.progress()
        self.assertEqual(result["data"]["solved_count"], 2)
        self.assertEqual(result["data"]["score"], 900)

    async def test_instance_info_no_secrets(self):
        from .conftest import FakeGateway

        gw = FakeGateway()
        gw.responses[("GET", "/scoreboard")] = {
            "success": True,
            "data": {"standings": []},
        }
        gw.responses[("GET", "/")] = {
            "status": 200,
            "text": "<html><title>CTFd</title> <footer>CTFd v3.5.3</footer></html>",
            "content_type": "text/html",
            "set_cookie": "",
        }
        c = build_client(gw)
        info = await c.instance_info()
        self.assertTrue(info["api_ok"])
        self.assertTrue(info["public_scoreboard"])
        self.assertEqual(info["detected_version"], "3.5.3")
        text = json.dumps(info)
        self.assertNotIn("session", text)
        self.assertNotIn("token", text)

    async def test_health_ok(self):
        from .conftest import FakeGateway

        gw = FakeGateway()
        gw.responses[("GET", "/challenges")] = challenge_page([], count=0)
        gw.responses[("GET", "/users/me")] = {
            "success": True,
            "data": {"id": 1, "name": "ops"},
        }
        c = build_client(gw)
        await c.set_token("tok")
        result = await c.health()
        self.assertEqual(result["status"], "ok")
        self.assertTrue(result["ctfd_reachable"])
        self.assertTrue(result["authenticated"])

    async def test_health_degraded_offline(self):
        from .conftest import FakeGateway

        gw = FakeGateway()
        gw.raise_exc = CTFdAPIError("Could not reach CTFd at x: TimeoutError", 0)
        c = build_client(gw)
        result = await c.health()
        self.assertEqual(result["status"], "error")
        self.assertFalse(result["ctfd_reachable"])


class PersistenceTests(unittest.IsolatedAsyncioTestCase):
    async def test_secrets_never_persisted_by_default(self):
        from server.ctfd_client import CTFdClient

        from .conftest import FakeGateway

        c = CTFdClient(gateway=FakeGateway())
        await c.set_token("ctfd_leaky_token_should_not_be_written")
        await c.set_cookie("session=leaky_cookie_should_not_be_written")
        state.set_creds("admin", "super-secret-password")

        content = state_manager.STATE_FILE.read_text(encoding="utf-8")
        self.assertNotIn("token", content)
        self.assertNotIn("cookie", content)
        self.assertNotIn("super-secret-password", content)
        self.assertNotIn("leaky", content)


if __name__ == "__main__":
    unittest.main()