"""Domain errors raised by the service layer.

Services are framework-free: they raise these instead of `fastapi.HTTPException`, and `main.py`
registers one handler that maps them to the same error envelope the rest of the app uses. This
keeps business rules (not-found / conflict / bad-request / bad-credentials) out of the routers and
independent of FastAPI. Detail strings are safe to surface (no PII); see CLAUDE.md.
"""

from __future__ import annotations


class ServiceError(Exception):
    """Base for expected business errors carrying an HTTP status and a safe detail message."""

    status_code: int = 500

    def __init__(self, detail: str) -> None:
        super().__init__(detail)
        self.detail = detail


class NotFoundError(ServiceError):
    status_code = 404

    def __init__(self, detail: str = "not found") -> None:
        super().__init__(detail)


class ConflictError(ServiceError):
    status_code = 409


class BadRequestError(ServiceError):
    status_code = 400


class UnauthorizedError(ServiceError):
    status_code = 401
