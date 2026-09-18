"""Health-check helper.

Kept as a thin wrapper around ``CTFdClient.health`` so existing imports
(``from .health import perform_health_check``) keep working.
"""

from __future__ import annotations

from typing import Any

from .ctfd_client import ctfd_client


async def perform_health_check() -> dict[str, Any]:
    return await ctfd_client.health()