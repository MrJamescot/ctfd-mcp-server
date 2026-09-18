"""MCP tool-layer tests: every documented tool exists and returns safe JSON."""

from __future__ import annotations

import asyncio
import json
import unittest

from server.ctfd_client import CTFdClient
from tests.conftest import FakeGateway, challenge_page


class McpToolTests(unittest.TestCase):
    async def _get_server(self):
        import ctfd_mcp_server

        return ctfd_mcp_server

    def test_all_documented_tools_are_registered(self):
        async def run():
            import ctfd_mcp_server

            tools = await ctfd_mcp_server.mcp.list_tools()
            return [t.name for t in tools]

        names = asyncio.run(run())
        expected = {
            "set_base_url", "set_token", "set_cookie", "login",
            "challenges", "challenge", "submit_flag", "scoreboard",
            "progress", "instance_info", "auth_status", "health", "download_file",
        }
        self.assertEqual(expected, set(names) & expected)
        self.assertGreaterEqual(len(names), len(expected))

    def _patch_client(self, gateway):
        """Swap the client used by ctfd_mcp_server with one on a fake gateway."""
        replacement = CTFdClient(gateway=gateway)

        def install(mcp_module):
            previous = mcp_module.ctfd_client
            mcp_module.ctfd_client = replacement
            return previous

        return install, replacement

    def test_submit_flag_returns_structured_error_without_confirm(self):
        async def run():
            mcp_module = await self._get_server()
            install, _repl = self._patch_client(FakeGateway())
            prev = install(mcp_module)
            try:
                out = await mcp_module.submit_flag(flag="flag{x}", challenge_id=1, confirm=False)
                payload = json.loads(out)
                self.assertEqual(payload["error"]["type"], "ValidationError")
                self.assertNotIn("flag{x}", out)
            finally:
                mcp_module.ctfd_client = prev

        asyncio.run(run())

    def test_set_token_never_echoes_the_token(self):
        async def run():
            mcp_module = await self._get_server()
            install, _repl = self._patch_client(FakeGateway())
            prev = install(mcp_module)
            try:
                out = await mcp_module.set_token("ctfd_should_not_show_me")
                self.assertNotIn("ctfd_should_not_show_me", out)
                self.assertIn("auth_mode", out)
            finally:
                mcp_module.ctfd_client = prev

        asyncio.run(run())

    def test_health_tool_returns_json(self):
        async def run():
            mcp_module = await self._get_server()
            gw = FakeGateway()
            gw.responses[("GET", "/challenges")] = challenge_page([], count=0)
            install, _repl = self._patch_client(gw)
            prev = install(mcp_module)
            try:
                out = await mcp_module.health()
                payload = json.loads(out)
                self.assertEqual(payload["status"], "ok")
                self.assertTrue(payload["ctfd_reachable"])
            finally:
                mcp_module.ctfd_client = prev

        asyncio.run(run())

    def test_challenge_tool_missing_challenge_is_structured_error(self):
        async def run():
            mcp_module = await self._get_server()
            from server.errors import CTFdAPIError

            gw = FakeGateway()
            gw.raise_exc = CTFdAPIError("CTFd returned 404 for GET /challenges/1.", 404)
            install, _repl = self._patch_client(gw)
            prev = install(mcp_module)
            try:
                out = await mcp_module.challenge("1")
                payload = json.loads(out)
                self.assertEqual(payload["error"]["type"], "ChallengeNotFoundError")
            finally:
                mcp_module.ctfd_client = prev

        asyncio.run(run())

    def test_login_tool_returns_mode_not_secret(self):
        async def run():
            mcp_module = await self._get_server()
            gw = FakeGateway()
            gw.responses[("GET", "/login")] = {
                "status": 200, "text": "", "content_type": "text/html", "set_cookie": "",
            }
            gw.responses[("POST", "/login")] = {
                "status": 302, "text": "", "content_type": "text/html",
                "set_cookie": "session=maskedcookie",
            }
            install, _repl = self._patch_client(gw)
            prev = install(mcp_module)
            try:
                out = await mcp_module.login("bob", "hunter2")
                self.assertNotIn("hunter2", out)
                self.assertNotIn("maskedcookie", out)
                self.assertIn("success", out)
            finally:
                mcp_module.ctfd_client = prev

        asyncio.run(run())


if __name__ == "__main__":
    unittest.main()