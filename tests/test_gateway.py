"""Gateway HTTP-decode tests: status codes, malformed bodies, error mapping."""

from __future__ import annotations

import unittest

from server.errors import (
    AuthenticationError,
    CTFdAPIError,
    ServerDownError,
)
from server.gateway import Gateway


class FakeResponse:
    def __init__(self, status: int, text: str, content_type: str = "application/json"):
        self.status = status
        self._text = text
        self.headers = {"Content-Type": content_type}

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
            await gw._decode("GET", "/x", FakeResponse(200, html, "text/html"), False)
        # The message never contains the raw body (avoids leaking page content).
        self.assertNotIn("login page", str(ctx.exception))

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
            await gw._decode("GET", "/x", FakeResponse(200, secret, "text/html"), False)
        self.assertNotIn("TOP_SECRET", str(ctx.exception))


if __name__ == "__main__":
    unittest.main()