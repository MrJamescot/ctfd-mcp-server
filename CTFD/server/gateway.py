import aiohttp

class Gateway:
    def __init__(self):
        # DEFAULT BASE (boleh diganti bebas)
        self.BASE = "https://demo.ctfd.io/api/v1"

    def set_base(self, url: str):
        self.BASE = url.rstrip("/")

    async def request(self, method: str, path: str, **kwargs):
        url = f"{self.BASE}{path}"

        async with aiohttp.ClientSession() as session:
            async with session.request(method, url, **kwargs) as r:
                try:
                    return await r.json()
                except:
                    return {"error": "invalid_json", "status": r.status, "text": await r.text()}


gateway = Gateway()
