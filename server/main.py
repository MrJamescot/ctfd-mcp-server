"""Optional FastAPI REST interface for the CTFd MCP server.

This mirrors the MCP tool layer over plain HTTP, which is convenient for
debugging, scripting, and Docker deployments.  It uses the exact same client
(``server.ctfd_client``) as the MCP server, so behaviour is identical.

Run with:  ``uvicorn server.main:app --host 0.0.0.0 --port 8000``
"""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager

import uvicorn
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse

from .config import settings
from .ctfd_client import ctfd_client
from .errors import (
    AuthenticationError,
    ChallengeNotFoundError,
    ConfigurationError,
    CTFdAPIError,
    CTFdError,
    ForbiddenError,
    SubmissionError,
    ValidationError,
)
from .gateway import gateway
from .models import BaseUrlModel, CookieModel, CredsModel, SubmitModel, TokenModel
from .session_manager import session_manager
from .setup import configure_from_env
from .state_manager import state

logger = logging.getLogger("ctfd.api")


@asynccontextmanager
async def lifespan(_app: FastAPI):
    configure_from_env()
    await session_manager.get_session()
    yield
    await session_manager.close()


app = FastAPI(title="CTFd MCP Server", version="1.0.0", lifespan=lifespan)


def _http_status_for(exc: CTFdError) -> int:
    if isinstance(exc, (ValidationError, ConfigurationError)):
        return 400
    if isinstance(exc, (AuthenticationError, ForbiddenError)):
        return 401
    if isinstance(exc, ChallengeNotFoundError):
        return 404
    if isinstance(exc, SubmissionError):
        return 422
    if isinstance(exc, CTFdAPIError):
        return 502 if exc.status >= 500 or exc.status == 0 else 400
    return 500


def _http_exc(exc: CTFdError) -> HTTPException:
    return HTTPException(status_code=_http_status_for(exc), detail=exc.to_dict())


@app.exception_handler(CTFdError)
async def ctfd_exception_handler(_request: Request, exc: CTFdError):
    return JSONResponse(status_code=_http_status_for(exc), content={"error": exc.to_dict()})


@app.exception_handler(HTTPException)
async def http_exception_handler(_request: Request, exc: HTTPException):
    return JSONResponse(status_code=exc.status_code, content={"error": exc.detail})


@app.exception_handler(Exception)  # last-resort catch-all boundary
async def generic_exception_handler(_request: Request, exc: Exception):
    logger.exception("Unhandled error: %s", type(exc).__name__)
    return JSONResponse(
        status_code=500,
        content={"error": {"type": "InternalServerError", "message": "Unexpected server error."}},
    )


# ---------------------------------------------------------------- routing

@app.post("/api/v1/set_base_url")
async def set_base_url(payload: BaseUrlModel):
    """Configure the CTFd instance this server talks to."""
    try:
        url = gateway.set_base(payload.url)
    except ConfigurationError as exc:
        raise HTTPException(status_code=400, detail=exc.to_dict()) from exc
    return {"status": "ok", "base_url": url}


@app.post("/api/v1/set_token")
async def set_token(payload: TokenModel):
    return await ctfd_client.set_token(payload.token)


@app.post("/api/v1/set_cookie")
async def set_cookie(payload: CookieModel):
    return await ctfd_client.set_cookie(payload.cookie)


@app.post("/api/v1/set_creds")
async def set_creds(payload: CredsModel):
    state.set_creds(payload.username, payload.password)
    return {"status": "ok", "auth_mode": state.auth_mode()}


@app.post("/api/v1/login")
async def login(payload: CredsModel):
    """Log in with username/password (creates a session cookie)."""
    return await ctfd_client.login(payload.username, payload.password)


@app.get("/api/v1/challenges")
async def list_challenges(
    category: str | None = None,
    search: str | None = None,
    solved: bool | None = None,
    page: int = 1,
    per_page: int = 25,
    max_pages: int = 10,
):
    return await ctfd_client.list_challenges(
        category=category,
        search=search,
        solved=solved,
        page=page,
        per_page=per_page,
        max_pages=max_pages,
    )


@app.get("/api/v1/challenges/{identifier}")
async def get_challenge(identifier: str):
    result = await ctfd_client.get_challenge(identifier)
    return {"success": True, "data": result}


@app.post("/api/v1/submit")
async def submit_flag(payload: SubmitModel):
    return await ctfd_client.submit_flag(
        flag=payload.flag,
        challenge_id=payload.challenge_id,
        challenge_name=payload.challenge_name,
        confirm=payload.confirm,
    )


@app.get("/api/v1/scoreboard")
async def scoreboard():
    return await ctfd_client.scoreboard()


@app.get("/api/v1/progress")
async def progress():
    return await ctfd_client.progress()


@app.get("/api/v1/instance_info")
async def instance_info():
    return await ctfd_client.instance_info()


@app.get("/api/v1/auth_status")
async def auth_status():
    return await ctfd_client.auth_status()


@app.get("/api/v1/health")
async def health():
    return await ctfd_client.health()


@app.get("/api/v1/files/{fid}/download")
async def download_file(fid: int):
    return await ctfd_client.download_challenge_file(fid, f"file_{fid}")


def run() -> None:
    """Console-script entry point: start the REST server with uvicorn."""
    uvicorn.run("server.main:app", host=settings.mcp_host, port=settings.mcp_port)


if __name__ == "__main__":
    run()