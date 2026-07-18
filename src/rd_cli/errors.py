"""Exception hierarchy for rd-cli.

Every failure the CLI can surface derives from :class:`RaindropError`, so the
top-level handler in ``cli.py`` catches one type and prints one clean message.
API failures carry the parsed ``errorMessage`` the Raindrop API returns, rather
than the bare HTTP status ``urllib`` would otherwise raise.
"""

from __future__ import annotations


class RaindropError(Exception):
    """Base class for every rd-cli error."""


class ConfigError(RaindropError):
    """A token could not be resolved, or config on disk is unreadable."""


class APIError(RaindropError):
    """The Raindrop API returned a non-success response.

    Attributes:
        status: HTTP status code, or ``None`` for transport-level failures.
        message: Human-readable message (the API's ``errorMessage`` when present).
        payload: The decoded JSON body, if any.
    """

    def __init__(
        self,
        message: str,
        *,
        status: int | None = None,
        payload: dict | None = None,
    ) -> None:
        super().__init__(message)
        self.status = status
        self.message = message
        self.payload = payload or {}

    def __str__(self) -> str:
        if self.status is not None:
            return f"HTTP {self.status}: {self.message}"
        return self.message


class AuthError(APIError):
    """Authentication failed (HTTP 401/403) — token missing, wrong, or expired."""


class NotFoundError(APIError):
    """The requested resource does not exist (HTTP 404)."""


class RateLimitError(APIError):
    """Rate limit exceeded (HTTP 429) and retries were exhausted."""
