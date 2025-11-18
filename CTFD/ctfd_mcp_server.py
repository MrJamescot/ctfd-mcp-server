import asyncio
import json
import httpx
from mcp.server.fastmcp import FastMCP
from mcp.types import TextContent


BACKEND = "http://127.0.0.1:8000"

client = httpx.AsyncClient(timeout=15.0)
mcp = FastMCP("ctfd")


async def backend_post(path, payload):
    url = f"{BACKEND}{path}"
    for _ in range(2):
        try:
            res = await client.post(url, json=payload)
            return res.json()
        except Exception:
            await asyncio.sleep(0.3)
    return {"error": "backend_unreachable"}


async def backend_get(path):
    url = f"{BACKEND}{path}"
    for _ in range(2):
        try:
            res = await client.get(url)
            return res.json()
        except Exception:
            await asyncio.sleep(0.3)
    return {"error": "backend_unreachable"}



@mcp.tool()
async def set_token(token: str):
    res = await backend_post("/api/v1/set_token", {"token": token})
    return TextContent(type="text", text=json.dumps(res, indent=2))


@mcp.tool()
async def set_cookie(cookie: str):
    res = await backend_post("/api/v1/set_cookie", {"cookie": cookie})
    return TextContent(type="text", text=json.dumps(res, indent=2))


@mcp.tool()
async def login(username: str, password: str):
    res = await backend_post("/api/v1/login", {"username": username, "password": password})
    return TextContent(type="text", text=json.dumps(res, indent=2))


@mcp.tool()
async def challenges(category: str | None = None):
    path = "/api/v1/challenges"
    if category:
        path += f"?category={category}"
    res = await backend_get(path)
    return TextContent(type="text", text=json.dumps(res, indent=2))


@mcp.tool()
async def challenge(identifier: str):
    res = await backend_get(f"/api/v1/challenges/{identifier}")
    return TextContent(type="text", text=json.dumps(res, indent=2))


@mcp.tool()
async def submit_flag(challenge_name: str | None, challenge_id: int | None, flag: str):
    payload = {
        "challenge_name": challenge_name,
        "challenge_id": challenge_id,
        "flag": flag,   
    }
    res = await backend_post("/api/v1/submit", payload)
    return TextContent(type="text", text=json.dumps(res, indent=2))


@mcp.tool()
async def scoreboard():
    res = await backend_get("/api/v1/scoreboard")
    return TextContent(type="text", text=json.dumps(res, indent=2))


@mcp.tool()
async def progress():
    res = await backend_get("/api/v1/progress")
    return TextContent(type="text", text=json.dumps(res, indent=2))


@mcp.tool()
async def health():
    res = await backend_get("/api/v1/health")
    return TextContent(type="text", text=json.dumps(res, indent=2))

@mcp.tool()
async def set_base_url(url: str):
    res = await backend_post("/api/v1/set_base_url", {"url": url})
    return TextContent(type="text", text=json.dumps(res, indent=2))



if __name__ == "__main__":
    mcp.run()
