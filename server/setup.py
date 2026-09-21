"""Shared startup bootstrap used by both the MCP and REST entry points."""

from __future__ import annotations

import logging

from .config import settings
from .errors import ConfigurationError
from .gateway import gateway
from .state_manager import state

logger = logging.getLogger("ctfd.setup")


def configure_from_env() -> None:
    """Apply environment-provided configuration and secrets (no echo)."""
    if settings.ctfd_base_url:
        try:
            gateway.set_base(settings.ctfd_base_url)
        except ConfigurationError as exc:
            logger.error("Invalid CTFD_BASE_URL: %s", exc.message)
    if settings.ctfd_admin_token:
        state.set_token(settings.ctfd_admin_token)
    if settings.ctfd_session_cookie:
        state.set_cookie(settings.ctfd_session_cookie)
    if settings.ctfd_username and settings.ctfd_password:
        state.set_creds(settings.ctfd_username, settings.ctfd_password)