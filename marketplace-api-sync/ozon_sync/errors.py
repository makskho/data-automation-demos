"""Exceptions shared by the HTTP layer and the client."""
from __future__ import annotations


class ApiError(Exception):
    """The API answered with an error status (or could not be reached: status 0)."""

    def __init__(self, status: int, message: str, body: object = None):
        super().__init__(f"HTTP {status}: {message}")
        self.status = status
        self.message = message
        self.body = body


class RateLimitError(ApiError):
    """HTTP 429. `retry_after` is the server hint in seconds, if it sent one."""

    def __init__(self, message: str = "Too Many Requests", retry_after: float | None = None, body: object = None):
        super().__init__(429, message, body)
        self.retry_after = retry_after


class TransportError(ApiError):
    """Network-level failure (DNS, refused connection, timeout)."""

    def __init__(self, message: str):
        super().__init__(0, message)


class SheetError(Exception):
    """The seller's spreadsheet cannot be read at all (no file, no SKU column)."""
