"""REST interface tests (server.main) with a mocked CTFd client."""

from __future__ import annotations

import unittest

from fastapi.testclient import TestClient

import server.ctfd_client as client_module
from server.ctfd_client import CTFdClient
from tests.conftest import FakeGateway, challenge_page, make_challenge


class RestTests(unittest.TestCase):
    def setUp(self):
        self.gw = FakeGateway()
        self.client_inst = CTFdClient(gateway=self.gw)
        self._restored_client = client_module.ctfd_client
        client_module.ctfd_client = self.client_inst
        import server.main as main_module

        main_module.ctfd_client = self.client_inst

    def tearDown(self):
        client_module.ctfd_client = self._restored_client

    def _client(self):
        from server.main import app

        return TestClient(app)

    def test_set_base_url_valid(self):
        c = self._client()
        with c:
            r = c.post("/api/v1/set_base_url", json={"url": "https://other.example"})
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json()["base_url"], "https://other.example")

    def test_set_base_url_invalid_is_rejected(self):
        c = self._client()
        with c:
            r = c.post("/api/v1/set_base_url", json={"url": "javascript:alert(1)"})
        self.assertEqual(r.status_code, 400)

    def test_challenges_endpoint(self):
        self.gw.responses[("GET", "/challenges")] = challenge_page(
            [make_challenge(1, "warmup", "misc", 50)], count=1, page=1, per_page=25
        )
        c = self._client()
        with c:
            r = c.get("/api/v1/challenges")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json()["count"], 1)
        self.assertEqual(r.json()["items"][0]["name"], "warmup")

    def test_submit_requires_confirm(self):
        c = self._client()
        with c:
            r = c.post("/api/v1/submit", json={"challenge_id": 1, "flag": "flag{x}"})
        self.assertEqual(r.status_code, 400)
        self.assertIn("confirm", r.json()["error"]["message"])

    def test_submit_success(self):
        self.gw.responses[("POST", "/challenges/attempt")] = {
            "success": True,
            "data": {"status": "correct", "message": "Correct", "points_earned": 100},
        }
        c = self._client()
        with c:
            r = c.post(
                "/api/v1/submit",
                json={"challenge_id": 1, "flag": "flag{real}", "confirm": True},
            )
        self.assertEqual(r.status_code, 200)
        self.assertTrue(r.json()["success"])

    def test_challenge_not_found_maps_to_404(self):
        from server.errors import CTFdAPIError

        self.gw.raise_exc = CTFdAPIError("CTFd returned 404 for GET /challenges/99.", 404)
        c = self._client()
        with c:
            r = c.get("/api/v1/challenges/99")
        self.assertEqual(r.status_code, 404)
        self.assertEqual(r.json()["error"]["type"], "ChallengeNotFoundError")

    def test_auth_status_endpoint(self):
        c = self._client()
        with c:
            r = c.get("/api/v1/auth_status")
        self.assertEqual(r.status_code, 200)
        self.assertFalse(r.json()["configured"])

    def test_health_endpoint(self):
        self.gw.responses[("GET", "/challenges")] = challenge_page([], count=0)
        c = self._client()
        with c:
            r = c.get("/api/v1/health")
        self.assertEqual(r.status_code, 200)
        self.assertTrue(r.json()["ctfd_reachable"])

    def test_health_endpoint_without_base_url(self):
        from server.ctfd_client import CTFdClient

        class NoBaseGW:
            def __init__(self):
                self.base = ""

            def set_base(self, url):
                self.base = url
                return url

            async def request(self, *a, **k):
                from server.errors import ConfigurationError

                raise ConfigurationError("CTFd base URL is not configured.")

        main_module = self._main_module()
        previous_api = main_module.ctfd_client
        main_module.ctfd_client = CTFdClient(gateway=NoBaseGW())
        try:
            c = self._client()
            with c:
                r = c.get("/api/v1/health")
            self.assertEqual(r.status_code, 200)
            self.assertEqual(r.json()["status"], "error")
        finally:
            main_module.ctfd_client = previous_api

    def _main_module(self):
        from server import main as main_module

        return main_module


class FileCacheTests(unittest.TestCase):
    def test_safe_filename_blocks_traversal(self):
        from server.file_cache import safe_filename, save_file

        name = safe_filename("../../etc/passwd")
        self.assertNotIn("..", name)
        self.assertNotIn("/", name)

        import tempfile

        from server.config import settings

        with tempfile.TemporaryDirectory() as tmp:
            previous = settings.file_cache_dir
            settings.file_cache_dir = tmp
            try:
                path = save_file("../../etc/passwd", b"not-a-password-file")
                self.assertTrue(path.startswith(tmp))
                self.assertNotIn("..", path)
            finally:
                settings.file_cache_dir = previous


if __name__ == "__main__":
    unittest.main()