"""Model Context Protocol (MCP) server for CTFd.

Runs the MCP tool layer directly on top of the reusable CTFd client
(``server.ctfd_client``).  Every tool returns structured JSON; credentials are
never echoed back and flags are never logged.

Usage:
    python ctfd_mcp_server.py                      # stdio transport (MCP clients)
    CTFD_MCP_TRANSPORT=sse python ctfd_mcp_server.py   # SSE over HTTP

Configuration comes from environment variables / ``.env``
(``CTFD_BASE_URL``, ``CTFD_ADMIN_TOKEN``, ...) and can be changed at runtime
via the ``set_base_url`` / ``set_token`` / ``set_cookie`` tools.
"""

from __future__ import annotations

import json
import logging
from typing import Any

from mcp.server.fastmcp import FastMCP

from server.config import settings
from server.ctfd_client import ctfd_client
from server.errors import CTFdError
from server.setup import configure_from_env

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")

mcp = FastMCP("ctfd")


def _ok(payload: Any) -> str:
    """Serialize a tool result as indented JSON text for the MCP client."""
    return json.dumps(payload, indent=2, default=str)


def _err(exc: CTFdError) -> str:
    """Serialize a structured error (never leaks credentials)."""
    return json.dumps({"error": exc.to_dict()}, indent=2)


@mcp.tool()
async def set_base_url(url: str) -> str:
    """Configure the CTFd instance this server talks to.

    Args:
        url: absolute http(s) URL of the CTFd instance, e.g. https://ctf.example.com
    """
    try:
        base = ctfd_client.gateway.set_base(url)
        return _ok({"success": True, "base_url": base})
    except CTFdError as exc:
        return _err(exc)


@mcp.tool()
async def set_token(token: str) -> str:
    """Use an API token for authentication (stored in memory only, never logged).

    Args:
        token: CTFd API access token.
    """
    try:
        return _ok(await ctfd_client.set_token(token))
    except CTFdError as exc:
        return _err(exc)


@mcp.tool()
async def set_cookie(cookie: str) -> str:
    """Use a session cookie for authentication (memory only, never logged).

    Args:
        cookie: full session cookie value, e.g. "session=abc..." or "name=..; session=..".
    """
    try:
        return _ok(await ctfd_client.set_cookie(cookie))
    except CTFdError as exc:
        return _err(exc)


@mcp.tool()
async def login(username: str, password: str) -> str:
    """Log in to CTFd with a username and password (kept in memory only).

    Creates a session cookie; the password is never returned.

    Args:
        username: CTFd account name.
        password: CTFd account password.
    """
    try:
        return _ok(await ctfd_client.login(username, password))
    except CTFdError as exc:
        return _err(exc)


@mcp.tool()
async def challenges(
    category: str | None = None,
    search: str | None = None,
    solved: bool | None = None,
    page: int = 1,
    per_page: int = 25,
) -> str:
    """List challenges with optional filters and pagination.

    Args:
        category: filter by challenge category (exact match).
        search: case-insensitive substring match on challenge name.
        solved: only show solved (True) or unsolved (False) challenges.
        page: page number (1-based) when no filters are applied.
        per_page: number of challenges per page (1-100).
    """
    try:
        return _ok(await ctfd_client.list_challenges(
            category=category, search=search, solved=solved,
            page=page, per_page=per_page,
        ))
    except CTFdError as exc:
        return _err(exc)


@mcp.tool()
async def challenge(identifier: str) -> str:
    """Get the full detail of a single challenge by numeric id or name.

    Includes description, category, value, files, hints and connection info.

    Args:
        identifier: challenge id (e.g. "3") or challenge name.
    """
    try:
        result = await ctfd_client.get_challenge(identifier)
        return _ok({"success": True, "data": result})
    except CTFdError as exc:
        return _err(exc)


@mcp.tool()
async def submit_flag(
    flag: str,
    challenge_name: str | None = None,
    challenge_id: int | None = None,
    confirm: bool = False,
) -> str:
    """Submit a flag for a challenge.

    Safety: requires confirm=True. Provide exactly one of challenge_id or
    challenge_name. The flag value is never logged.

    Args:
        flag: the flag to submit.
        challenge_name: name of the challenge to submit against.
        challenge_id: numeric id of the challenge to submit against.
        confirm: must be set to True as an explicit submission opt-in.
    """
    try:
        return _ok(await ctfd_client.submit_flag(
            flag=flag,
            challenge_name=challenge_name,
            challenge_id=challenge_id,
            confirm=confirm,
        ))
    except CTFdError as exc:
        return _err(exc)


@mcp.tool()
async def download_file(
    file_url: str, dest_dir: str | None = None
) -> str:
    """Download a challenge attachment to the local machine.

    Challenge detail (``challenge`` tool) returns a ``files`` array with
    site-relative paths like ``/files/<hash>/<name>`` (signed URLs on some
    deployments).  Pass one of those values here.

    Args:
        file_url: absolute http(s) URL or site-relative path to the file.
        dest_dir: optional local directory to store the file in (default:
            CTFD_DOWNLOAD_DIR or ./downloads).
    """
    try:
        return _ok(await ctfd_client.download_file(file_url, dest_dir=dest_dir))
    except CTFdError as exc:
        return _err(exc)


@mcp.tool()
async def unlock_hint(hint_id: int) -> str:
    """Unlock a challenge hint and return its content.

    WARNING: on CTFd a hint with a non-zero ``cost`` deducts that many points
    from your account.  When two hint IDs are needed (e.g. a hint's
    prerequisites), unlock them in order.

    Args:
        hint_id: numeric id of the hint (see the ``challenge`` tool result).
    """
    try:
        return _ok(await ctfd_client.unlock_hint(hint_id))
    except CTFdError as exc:
        return _err(exc)


@mcp.tool()
async def scoreboard() -> str:
    """Return the public CTFd scoreboard (top standings)."""
    try:
        return _ok(await ctfd_client.scoreboard())
    except CTFdError as exc:
        return _err(exc)


@mcp.tool()
async def progress() -> str:
    """Return the authenticated user's progress (score and solved challenges)."""
    try:
        return _ok(await ctfd_client.progress())
    except CTFdError as exc:
        return _err(exc)


@mcp.tool()
async def instance_info() -> str:
    """Return safe, public metadata about the configured CTFd instance.

    No secrets are included.
    """
    try:
        return _ok(await ctfd_client.instance_info())
    except CTFdError as exc:
        return _err(exc)


@mcp.tool()
async def auth_status() -> str:
    """Report whether the current session is authenticated and which auth mode is active.

    Reveals no tokens/cookies/passwords.
    """
    try:
        return _ok(await ctfd_client.auth_status())
    except CTFdError as exc:
        return _err(exc)


@mcp.tool()
async def health() -> str:
    """Perform a health check: CTFd reachability, API status and authentication state."""
    try:
        return _ok(await ctfd_client.health())
    except CTFdError as exc:
        return _err(exc)


def main() -> None:
    configure_from_env()
    transport = settings.mcp_transport
    if transport == "sse":
        mcp.run(transport="sse")
    else:
        mcp.run()


if __name__ == "__main__":
    main()