import json
from pathlib import Path
from typing import Optional, Dict, Any

STATE_FILE = Path("./server_state.json")

class StateManager:
    def __init__(self):
        self.state = {
            "token": None,
            "cookie": None,
            "username": None,
            "password": None,
            "challenge_map": {},
            "last_health": None,
            "base_url": None,   # NEW FIX
        }
        self._load()

    def _load(self):
        if STATE_FILE.exists():
            try:
                self.state.update(json.loads(STATE_FILE.read_text()))
            except:
                pass

    def _save(self):
        try:
            STATE_FILE.write_text(json.dumps(self.state, indent=2))
        except:
            pass

    def set_token(self, token: str):
        self.state["token"] = token
        self._save()

    def set_cookie(self, cookie: str):
        self.state["cookie"] = cookie
        self._save()

    def set_creds(self, username: str, password: str):
        self.state["username"] = username
        self.state["password"] = password
        self._save()

    def update_challenge_map(self, name: str, cid: int):
        self.state["challenge_map"][name] = cid
        self._save()

    def get_mapped_id(self, name: str) -> Optional[int]:
        return self.state["challenge_map"].get(name)

    def set_last_health(self, obj: Dict[str, Any]):
        self.state["last_health"] = obj
        self._save()

    def get_last_health(self):
        return self.state.get("last_health")


    def set_base_url(self, url: str):
        self.state["base_url"] = url
        self._save()

    def get_base_url(self) -> Optional[str]:
        return self.state.get("base_url")


state = StateManager()
