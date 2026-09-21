"""Gateway HTTP-decode tests: status codes, malformed bodies, error mapping."""

from __future__ import annotations

import unittest

from server.errors import (
    AuthenticationError,
    ConfigurationError,
    CTFdAPIError,
    ServerDownError,
)
from server.gateway import Gateway
from server.session_manager import session_manager
from server.state_manager import state


class _Headers(dict):
    def getall(self, key: str, default=None):
        value = self.get(key)
        if value is None:
            return default if default is not None else []
        if isinstance(value, list):
            return value
        return [value]


class FakeResponse:
    def __init__(self, status: int, text: str, content_type: str = "application/json"):
        self.status = status
        self._text = text
        self.headers = _Headers({"Content-Type": content_type})

    def getall(self, key, default=None):
        return self.headers.getall(key, default)

    async def text(self) -> str:
        return self._text


class GatewayDecodeTests(unittest.IsolatedAsyncioTestCase):
    async def test_json_parsed(self):
        gw = Gateway()
        out = await gw._decode("GET", "/x", FakeResponse(200, '{"success": true, "data": []}'), False)
        self.assertEqual(out["data"], [])

    async def test_non_json_raises_api_error(self):
        gw = Gateway()
        html = "<html><body>CTFd login page</body></html>"
        with self.assertRaises(CTFdAPIError) as ctx:
            await gw._decode(
                "GET", "/x", FakeResponse(200, html, "text/html"), False, use_api=False
            )
        # The message never contains the raw body (avoids leaking page content).
        self.assertNotIn("login page", str(ctx.exception))

    async def test_html_at_api_is_authentication_error(self):
        # Reverse-proxied CTFd deployments bounce anonymous /api/v1 calls to an
        # HTML landing/login page with HTTP 200 instead of a 302/401/403.
        gw = Gateway()
        html = "<!DOCTYPE html><title>Pwny CTF</title><a href=\"/files/\">files</a>"
        with self.assertRaises(AuthenticationError):
            await gw._decode(
                "GET", "/challenges", FakeResponse(200, html, "text/html"), True
            )

    async def test_401_maps_to_authentication_error(self):
        gw = Gateway()
        with self.assertRaises(AuthenticationError):
            await gw._decode("GET", "/x", FakeResponse(401, '{"success": false}'), False)

    async def test_403_maps_to_authentication_error(self):
        gw = Gateway()
        with self.assertRaises(AuthenticationError):
            await gw._decode("GET", "/x", FakeResponse(403, '{"success": false}'), False)

    async def test_5xx_maps_to_server_down(self):
        gw = Gateway()
        with self.assertRaises(ServerDownError):
            await gw._decode("GET", "/x", FakeResponse(503, '{"success": false}'), False)

    async def test_success_false_raises_unless_allowed(self):
        gw = Gateway()
        body = '{"success": false, "errors": ["not allowed"]}'
        with self.assertRaises(CTFdAPIError) as ctx:
            await gw._decode("GET", "/x", FakeResponse(200, body), False)
        self.assertIn("not allowed", str(ctx.exception))
        # allow_failure returns the payload untouched (flag-attempt path).
        out = await gw._decode("GET", "/x", FakeResponse(200, body), True)
        self.assertFalse(out["success"])

    async def test_404_json_maps_to_api_error(self):
        gw = Gateway()
        with self.assertRaises(CTFdAPIError) as ctx:
            await gw._decode("GET", "/challenges/9", FakeResponse(404, '{"success": false}'), False)
        self.assertEqual(ctx.exception.status, 404)

    async def test_errors_never_leak_body_content(self):
        gw = Gateway()
        secret = "SET-Cookie: session=TOP_SECRET"
        with self.assertRaises(CTFdAPIError) as ctx:
            await gw._decode(
                "GET", "/x", FakeResponse(200, secret, "text/html"), False, use_api=False
            )
        self.assertNotIn("TOP_SECRET", str(ctx.exception))


class HostGuardTests(unittest.IsolatedAsyncioTestCase):
    """C3: private/loopback/metadata URLs are blocked by default."""

    def _gw(self):
        gw = Gateway()
        gw._base = None
        return gw

    async def test_private_loopback_blocked(self):
        from server.config import settings

        previous = settings.ctfd_allow_private_ips
        settings.ctfd_allow_private_ips = False
        try:
            with self.assertRaises(ConfigurationError):
                self._gw().set_base("http://127.0.0.1:8000")
            with self.assertRaises(ConfigurationError):
                self._gw().set_base("http://[::1]:8000")
        finally:
            settings.ctfd_allow_private_ips = previous

    async def test_metadata_and_link_local_blocked(self):
        from server.config import settings

        previous = settings.ctfd_allow_private_ips
        settings.ctfd_allow_private_ips = False
        try:
            for url in (
                "http://169.254.169.254/latest/meta-data/",
                "http://10.0.0.5/",
                "http://192.168.1.10/",
            ):
                with self.assertRaises(ConfigurationError):
                    self._gw().set_base(url)
        finally:
            settings.ctfd_allow_private_ips = previous

    async def test_public_url_allowed(self):
        from server.config import settings

        previous = settings.ctfd_allow_private_ips
        settings.ctfd_allow_private_ips = False
        try:
            base = self._gw().set_base("https://ctf.example.com")
            self.assertEqual(base, "https://ctf.example.com")
        finally:
            settings.ctfd_allow_private_ips = previous

    async def test_opted_into_private_allowed(self):
        from server.config import settings

        previous = settings.ctfd_allow_private_ips
        settings.ctfd_allow_private_ips = True
        try:
            base = self._gw().set_base("http://127.0.0.1:8000")
            self.assertEqual(base, "http://127.0.0.1:8000")
        finally:
            settings.ctfd_allow_private_ips = previous

    async def test_request_still_guards_settings_fallback(self):
        from server.config import settings

        previous = settings.ctfd_allow_private_ips
        settings.ctfd_allow_private_ips = False
        try:
            gw = self._gw()
            state._base_url = "http://10.0.0.7"  # bypass set_base validation
            with self.assertRaises(ConfigurationError):
                await gw.request("GET", "/challenges")
            state._base_url = None
        finally:
            settings.ctfd_allow_private_ips = previous


class _Ctrl:
    def __init__(self, body: str):
        self._resp = FakeResponse(200, body)

    async def __aenter__(self):
        return self._resp

    async def __aexit__(self, *args):
        return False


class _FakeHttpSession:
    def __init__(self):
        self.calls = []

    def request(self, method, url, **kwargs):
        self.calls.append((method, url, kwargs))
        return _Ctrl('{"success": true, "data": []}')


class RequestHeaderTests(unittest.IsolatedAsyncioTestCase):
    """A1/A2: CSRF-Token for cookie-mode mutations, JSON content-type for tokens."""

    def _install_fake_session(self):
        fake = _FakeHttpSession()
        original = session_manager.get_session

        async def _fake_get_session():
            return fake

        session_manager.get_session = _fake_get_session
        return fake, original

    def setUp(self):
        self.gw = Gateway()
        self.gw._base = "https://ctf.example.com"
        session_manager.set_csrf_nonce(None)

    def tearDown(self):
        state.set_token("")
        state.set_cookie("")
        state.set_creds("", "")

    async def test_token_mode_sends_json_content_type(self):
        fake, original = self._install_fake_session()
        try:
            state.set_token("ctfd_tok_123")
            await self.gw.request("GET", "/challenges")
            headers = fake.calls[0][2]["headers"]
            self.assertEqual(headers.get("Content-Type"), "application/json")
        finally:
            session_manager.get_session = original

    async def test_cookie_mode_post_sends_csrf_token(self):
        fake, original = self._install_fake_session()
        try:
            state.set_cookie("session=abc123")
            session_manager.set_csrf_nonce("nonce_a1b2c3")
            await self.gw.request("POST", "/challenges/attempt", json={})
            headers = fake.calls[0][2]["headers"]
            self.assertEqual(headers.get("CSRF-Token"), "nonce_a1b2c3")
        finally:
            session_manager.get_session = original

    async def test_cookie_mode_get_has_no_csrf(self):
        fake, original = self._install_fake_session()
        try:
            state.set_cookie("session=abc123")
            session_manager.set_csrf_nonce("nonce_a1b2c3")
            await self.gw.request("GET", "/challenges")
            self.assertNotIn("CSRF-Token", fake.calls[0][2]["headers"])
        finally:
            session_manager.get_session = original

    async def test_token_mode_post_has_no_csrf(self):
        fake, original = self._install_fake_session()
        try:
            state.set_token("ctfd_tok_123")
            session_manager.set_csrf_nonce("nonce_a1b2c3")
            await self.gw.request("POST", "/challenges/attempt", json={})
            self.assertNotIn("CSRF-Token", fake.calls[0][2]["headers"])
        finally:
            session_manager.get_session = original

    async def test_non_api_request_skips_extra_headers(self):
        fake, original = self._install_fake_session()
        try:
            state.set_token("ctfd_tok_123")
            session_manager.set_csrf_nonce("nonce_a1b2c3")
            await self.gw.request("POST", "/login", use_api=False, raw=True, data={})
            headers = fake.calls[0][2].get("headers", {})
            self.assertNotIn("Content-Type", headers)
            self.assertNotIn("CSRF-Token", headers)
        finally:
            session_manager.get_session = original


if __name__ == "__main__":
    unittest.main()