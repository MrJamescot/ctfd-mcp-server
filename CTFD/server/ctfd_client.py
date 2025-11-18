import aiohttp
from server.gateway import gateway
from .state_manager import state
from .session_manager import session_manager
from .errors import ForbiddenError, ServerDownError
from .file_cache import save_file


class CTFdClient:
    async def login(self, username: str, password: str):
        sess = await session_manager.get_session()

        payload = {
            "name": username,
            "password": password
        }

        async with sess.post(
            f"{gateway.BASE}/users/login",
            json=payload
        ) as r:
            if r.status == 200:
                data = await r.json()
                token = data.get("data", {}).get("token")

                if token:
                    state.set_creds(username, password)
                    state.set_token(token)
                    await session_manager.refresh_headers()
                    return {"success": True, "token": token}

            return {"success": False, "error": await r.text()}

    async def refresh_login(self):
        username = state.state["username"]
        password = state.state["password"]

        if not username or not password:
            return {"success": False, "error": "no_credentials"}

        return await self.login(username, password)

    async def list_challenges(self):
        res = await gateway.request("GET", "/challenges")

        if "error" in res:
            if res["error"] == "forbidden":
                await self.refresh_login()
                res = await gateway.request("GET", "/challenges")

            if "error" in res:
                raise ServerDownError("Challenges API unreachable.")

        challenges = res.get("data", [])
        for ch in challenges:
            name = ch.get("name")
            cid = ch.get("id")
            if name and cid:
                state.update_challenge_map(name, cid)

        return challenges

    async def get_challenge(self, name: str):
        cid = state.get_mapped_id(name)

        if not cid:
            await self.list_challenges()
            cid = state.get_mapped_id(name)

        if not cid:
            return {"error": "challenge_not_found"}

        res = await gateway.request("GET", f"/challenges/{cid}")

        if "error" in res:
            if res["error"] == "forbidden":
                await self.refresh_login()
                res = await gateway.request("GET", f"/challenges/{cid}")

        return res.get("data")

    async def download_challenge_file(self, file_id: int, filename: str):
        sess = await session_manager.get_session()

        async with sess.get(
            f"{gateway.BASE}/files/{file_id}/download"
        ) as r:
            if r.status != 200:
                return {"error": r.status, "detail": await r.text()}

            data = await r.read()
            path = save_file(filename, data)
            return {"success": True, "path": path}

    async def submit_flag(self, challenge_name: str, flag: str):
        cid = state.get_mapped_id(challenge_name)

        if not cid:
            await self.list_challenges()
            cid = state.get_mapped_id(challenge_name)

        if not cid:
            return {"error": "challenge_not_found"}

        payload = {"challenge_id": cid, "submission": flag}

        res = await gateway.request("POST", "/challenges/attempt", json=payload)

        if "error" in res:
            if res["error"] == "forbidden":
                await self.refresh_login()
                res = await gateway.request("POST", "/challenges/attempt", json=payload)

        return res


ctfd_client = CTFdClient()
