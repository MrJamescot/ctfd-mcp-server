"""Structured error types shared by the MCP layer, the REST layer and the client.

The public ``message`` of every exception is safe to show to a user or an AI
agent: it never contains tokens, cookies, passwords or flags.  Detailed
diagnostics may additionally be attached in ``detail`` (also redacted).
"""

from __future__ import annotations


class CTFdError(Exception):
    """Base class for every error raised by this package."""

    def __init__(self, message: str, *, detail: str | None = None):
        super().__init__(message)
        self.message = message
        self.detail = detail

    def to_dict(self) -> dict:
        """Return a safe, JSON-serialisable representation of the error."""
        payload = {"type": type(self).__name__, "message": self.message}
        if self.detail:
            payload["detail"] = self.detail
        return payload


class ConfigurationError(CTFdError):
    """The server is missing or misconfigured (e.g. no valid BASE_URL)."""


class ValidationError(CTFdError):
    """A tool/endpoint received invalid user input."""


class AuthenticationError(CTFdError):
    """The request was rejected or could not be authenticated."""


class CTFdAPIError(CTFdError):
    """CTFd returned a status/body we could not interpret.

    ``status`` is the HTTP status code (0 for transport-level failures).
    """

    def __init__(self, message: str, status: int, *, detail: str | None = None):
        super().__init__(message, detail=detail)
        self.status = status


class ChallengeNotFoundError(CTFdError):
    """A challenge with the requested id/name does not exist (or is hidden)."""


class SubmissionError(CTFdError):
    """A flag could not be submitted (rate limited, malformed, etc.)."""


class ServerDownError(CTFdAPIError):
    """Backwards-compatible alias: CTFd was unreachable or returned 5xx."""


class ForbiddenError(AuthenticationError):
    """Backwards-compatible alias: the CTFd API denied access (401/403)."""