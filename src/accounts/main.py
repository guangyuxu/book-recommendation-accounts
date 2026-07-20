"""FastAPI application: the accounts (IdP + CRUD) entrypoint.

Wires logging, the correlation-id middleware, CORS, health/readiness probes, a uniform error
envelope, and the feature routers: the external face (auth/signup, family CRUD) protected by the
user token, and the internal face (/internal/*) protected by the service token.
"""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

from dishka import Container
from dishka.integrations.fastapi import setup_dishka
from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy import text

from .config import get_settings
from .container import build_container
from .db import session_scope
from .errors import ServiceError
from .logging import configure_logging, request_id_var
from .middleware import CorrelationIdMiddleware
from .routers import auth, family, internal

logger = logging.getLogger(__name__)


def _request_id(request: Request) -> str:
    return getattr(request.state, "request_id", None) or request_id_var.get()


def _envelope(request: Request, status_code: int, message: Any) -> JSONResponse:
    """Uniform error envelope carrying the correlation id."""
    return JSONResponse(
        status_code=status_code,
        content={
            "error": {
                "code": status_code,
                "message": message,
                "request_id": _request_id(request),
            }
        },
    )


def create_app(container: Container | None = None) -> FastAPI:
    """Build and configure the FastAPI app.

    `container` lets tests inject a DI container with overridden providers; production builds the
    default one. The container is closed on shutdown so its APP-scoped resources are released.
    """
    configure_logging()
    settings = get_settings()
    container = container or build_container()

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        yield
        container.close()

    app = FastAPI(
        title="Book Recommendation Accounts",
        version="0.0.1",
        summary="Identity provider + family/child CRUD for the book-recommendation platform.",
        lifespan=lifespan,
    )

    app.add_middleware(CorrelationIdMiddleware)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origin_list,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
        expose_headers=["X-Request-Id"],
    )

    @app.exception_handler(HTTPException)
    async def _http_exc(request: Request, exc: HTTPException) -> JSONResponse:
        return _envelope(request, exc.status_code, exc.detail)

    @app.exception_handler(ServiceError)
    async def _service_exc(request: Request, exc: ServiceError) -> JSONResponse:
        # Domain errors from the service layer map to the same envelope (detail is PII-safe).
        return _envelope(request, exc.status_code, exc.detail)

    @app.exception_handler(RequestValidationError)
    async def _validation_exc(
        request: Request, exc: RequestValidationError
    ) -> JSONResponse:
        return _envelope(request, 422, exc.errors())

    @app.exception_handler(Exception)
    async def _unhandled_exc(request: Request, exc: Exception) -> JSONResponse:
        # PII-safe: log only the exception type, never its message/args.
        logger.exception("unhandled error: %s", type(exc).__name__)
        return _envelope(request, 500, "internal server error")

    @app.get("/healthz", tags=["health"])
    def healthz() -> dict[str, str]:
        """Liveness probe: the process is up (no dependency checks)."""
        return {"status": "ok"}

    @app.get("/readyz", tags=["health"])
    def readyz() -> JSONResponse:
        """Readiness probe: verify the DB (this service owns the account tables) is reachable."""
        db_ok = _check_db()
        return JSONResponse(
            status_code=200 if db_ok else 503,
            content={
                "status": "ok" if db_ok else "degraded",
                "checks": {"db": db_ok},
            },
        )

    app.include_router(auth.router)
    app.include_router(family.router)
    app.include_router(internal.router)

    setup_dishka(container, app)
    return app


def _check_db() -> bool:
    try:
        with session_scope() as session:
            session.execute(text("SELECT 1"))
        return True
    except Exception as exc:  # noqa: BLE001 — readiness must never raise
        logger.warning("db readiness check failed: %s", type(exc).__name__)
        return False


app = create_app()
