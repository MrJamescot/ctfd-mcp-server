import aiohttp
from .state_manager import state

class SessionManager:
    def __init__(self):
        self.session = None

    async def get_session(self):
        if self.session:
            return self.session

        headers = {
            "User-Agent": "Mozilla/5.0",
        }

        if state.state["cookie"]:
            headers["Cookie"] = state.state["cookie"]

        if state.state["token"]:
            headers["Authorization"] = f"Token {state.state['token']}"

        self.session = aiohttp.ClientSession(headers=headers)
        return self.session

    async def refresh_headers(self):
        if not self.session:
            return

        if state.state["cookie"]:
            self.session.headers["Cookie"] = state.state["cookie"]

        if state.state["token"]:
            self.session.headers["Authorization"] = f"Token {state.state['token']}"

    async def close(self):
        if self.session:
            await self.session.close()
            self.session = None


session_manager = SessionManager()
