from __future__ import annotations


class BazikError(RuntimeError):
    """Raised when the Bazik API returns an error or an unexpected response."""

    def __init__(self, message: str, status_code: int | None = None, body: str | None = None):
        super().__init__(message)
        self.status_code = status_code
        self.body = body
