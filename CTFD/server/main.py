import uvicorn
import asyncio
from fastapi import FastAPI, BackgroundTasks, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from .config import settings
from .ctfd_client import ctfd_client
from .state_manager import state
from .session_manager import session_manager
from .health import perform_health_check
from .utils import ensure_cache_dir
from server.gateway import gateway


CTFD_BASE = "https://demo.ctfd.io"   # ← BASE URL FIXED

class TokenModel(BaseModel):
    token: str

class CookieModel(BaseModel):
    cookie: str

class CredsModel(BaseModel):
    username: str
    password: str

class SubmitModel(BaseModel):
    challenge_name: str | None = None
    challenge_id: int | None = None
    flag: str


app = FastAPI(title="CTFd MCP Server")


@app.on_event("startup")
async def startup_event():
    ensure_cache_dir()

    # force set base URL always to demo.ctfd.io
    gateway.set_base(CTFD_BASE)
    state.set_base_url(CTFD_BASE)

    try:
        await session_manager.get_session()
    except:
        pass

    try:
        await asyncio.wait_for(perform_health_check(), 10.0)
    except:
        pass


@app.post("/api/v1/set_base_url")
async def set_base_url():
    # ignore user input → always use demo.ctfd.io
    url = CTFD_BASE
    gateway.set_base(url)
    state.set_base_url(url)
    return {"status": "ok", "base_url": url}


@app.on_event("shutdown")
async def shutdown_event():
    try:
        await session_manager.close()
    except Exception:
        pass


@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException):
    return JSONResponse(status_code=exc.status_code, content={"error": exc.detail})


@app.exception_handler(Exception)
async def generic_exception_handler(request: Request, exc: Exception):
    return JSONResponse(status_code=500, content={"error": str(exc)})


@app.post("/api/v1/set_token")
async def set_token(payload: TokenModel):
    state.set_token(payload.token)
    try:
        await session_manager.refresh_headers()
    except Exception:
        pass
    return {"status": "token_set"}


@app.post("/api/v1/set_cookie")
async def set_cookie(payload: CookieModel):
    state.set_cookie(payload.cookie)
    try:
        await session_manager.refresh_headers()
    except Exception:
        pass
    return {"status": "cookie_set"}


@app.post("/api/v1/set_creds")
async def set_creds(payload: CredsModel):
    state.set_creds(payload.username, payload.password)
    return {"status": "creds_set"}


@app.post("/api/v1/login")
async def login(payload: CredsModel | None = None):
    if payload:
        state.set_creds(payload.username, payload.password)
    username = state.state.get("username")
    password = state.state.get("password")
    if not username or not password:
        raise HTTPException(status_code=400, detail="no_credentials")
    return await ctfd_client.login(username, password)


@app.get("/api/v1/challenges")
async def list_challenges(category: str | None = None):
    try:
        chs = await ctfd_client.list_challenges()
        if category:
            chs = [c for c in chs if c.get("category") == category]
        return {"data": chs}
    except HTTPException as e:
        raise e
    except Exception as e:
        raise HTTPException(status_code=502, detail=str(e))


@app.get("/api/v1/challenges/{identifier}")
async def get_challenge(identifier: str):
    try:
        if identifier.isdigit():
            cid = int(identifier)
            if hasattr(ctfd_client, "get_challenge_by_id"):
                res = await ctfd_client.get_challenge_by_id(cid)
                if res:
                    return {"data": res}
            res = await ctfd_client.get_challenge(str(cid))
            return {"data": res}
        else:
            return {"data": await ctfd_client.get_challenge(identifier)}
    except HTTPException as e:
        raise e
    except Exception as e:
        raise HTTPException(status_code=502, detail=str(e))


@app.post("/api/v1/submit")
async def submit_flag(payload: SubmitModel):
    if not payload.flag:
        raise HTTPException(status_code=400, detail="no_flag")

    if payload.challenge_id:
        name = None
        for n, cid in state.state.get("challenge_map", {}).items():
            if cid == payload.challenge_id:
                name = n
                break
        if not name:
            raise HTTPException(status_code=404, detail="challenge_not_mapped")
        return await ctfd_client.submit_flag(name, payload.flag)

    if payload.challenge_name:
        return await ctfd_client.submit_flag(payload.challenge_name, payload.flag)

    raise HTTPException(status_code=400, detail="no_challenge_specified")


@app.get("/api/v1/scoreboard")
async def scoreboard():
    try:
        res = await ctfd_client.get_scoreboard() if hasattr(ctfd_client, "get_scoreboard") else None
        if res is None:
            raise HTTPException(status_code=502, detail="scoreboard_unavailable")
        return {"data": res}
    except Exception as e:
        raise HTTPException(status_code=502, detail=str(e))


@app.get("/api/v1/progress")
async def progress():
    try:
        res = await ctfd_client.get_user_progress() if hasattr(ctfd_client, "get_user_progress") else None
        if res is None:
            raise HTTPException(status_code=502, detail="progress_unavailable")
        return {"data": res}
    except Exception as e:
        raise HTTPException(status_code=502, detail=str(e))


@app.get("/api/v1/files/{fid}/download")
async def download_file(fid: int):
    try:
        return await ctfd_client.download_challenge_file(fid, f"file_{fid}")
    except Exception as e:
        raise HTTPException(status_code=502, detail=str(e))


@app.get("/api/v1/health")
async def health():
    last = state.get_last_health()
    try:
        if not last:
            last = await perform_health_check()
        return {"status": "ok", "health": last}
    except Exception as e:
        return {"status": "error", "error": str(e), "health": last}


if __name__ == "__main__":
    uvicorn.run("server.main:app", host=settings.mcp_host, port=settings.mcp_port, reload=True)
