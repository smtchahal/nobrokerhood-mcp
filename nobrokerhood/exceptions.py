class NobrokerhoodError(Exception):
    """Base exception for all Nobrokerhood API errors."""


class AuthError(NobrokerhoodError):
    """Raised when the API returns an authentication/session error."""

    def __init__(self, message: str, response_body: dict | None = None):
        self.response_body = response_body
        super().__init__(message)


class APIError(NobrokerhoodError):
    """Raised when the API returns a non-2xx response."""

    def __init__(
        self, status_code: int, message: str, response_body: dict | None = None
    ):
        self.status_code = status_code
        self.response_body = response_body
        super().__init__(f"HTTP {status_code}: {message}")
