"""FastAPI application entry point."""

import asyncio
from contextlib import asynccontextmanager
from collections.abc import AsyncGenerator
from datetime import UTC, datetime

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import JSONResponse

from app.api.v1.router import api_router
from app.config import settings
from app.core.exceptions import AppException
from app.core.middleware import (
    RateLimitMiddleware,
    RequestLoggingMiddleware,
    SecurityHeadersMiddleware,
)
from app.core.background_tasks import (
    run_startup_health_check,
    start_health_check_scheduler,
    stop_health_check_scheduler,
)
from app.database import init_db, close_db

# Background task handle
_health_check_task: asyncio.Task | None = None


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Application lifespan events."""
    global _health_check_task

    # ---- STARTUP ----
    import os
    print(f"Environment: {settings.environment}")
    print(f"PORT: {os.environ.get('PORT', 'not set')}")
    print(f"DATABASE_URL set: {bool(os.environ.get('DATABASE_URL'))}")
    print(f"Resolved DB URL: {settings.database_url.split('@')[-1] if '@' in settings.database_url else 'no-auth-found'}")
    print(f"SSL required: {settings.database_requires_ssl}")

    # Retry DB init (Postgres may not be ready yet)
    for attempt in range(10):
        try:
            await init_db()
            print("Database initialized successfully")
            break
        except Exception as e:
            print(f"Database not ready (attempt {attempt + 1}/10): {e}")
            await asyncio.sleep(3)
    else:
        raise RuntimeError("Database never became ready")

    # Run startup health check (non-blocking)
    asyncio.create_task(run_startup_health_check())

    # Start 24-hour health check scheduler
    _health_check_task = asyncio.create_task(start_health_check_scheduler())

    yield

    # ---- SHUTDOWN ----
    stop_health_check_scheduler()

    if _health_check_task:
        _health_check_task.cancel()
        try:
            await _health_check_task
        except asyncio.CancelledError:
            pass

    await close_db()


def create_application() -> FastAPI:
    """Create and configure the FastAPI application."""
    app = FastAPI(
        title=settings.app_name,
        version=settings.app_version,
        description="VOLO AI - Hospitality Marketplace API",
        docs_url="/docs" if settings.environment != "production" else None,
        redoc_url="/redoc" if settings.environment != "production" else None,
        openapi_url="/openapi.json" if settings.environment != "production" else None,
        lifespan=lifespan,
    )

    # Exception handlers
    @app.exception_handler(AppException)
    async def app_exception_handler(
        request: Request, exc: AppException
    ) -> JSONResponse:
        return JSONResponse(
            status_code=exc.status_code,
            content={"detail": exc.detail},
            headers=exc.headers,
        )

    # Middleware (order matters)
    app.add_middleware(SecurityHeadersMiddleware)

    if settings.environment != "development":
        app.add_middleware(
            RateLimitMiddleware,
            requests_per_minute=settings.rate_limit_per_minute,
        )

    app.add_middleware(RequestLoggingMiddleware)

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=False,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.add_middleware(GZipMiddleware, minimum_size=1000)

    # Routes
    app.include_router(api_router, prefix=settings.api_prefix)

    @app.get("/health")
    async def health_check() -> dict:
        return {
            "status": "healthy",
            "version": settings.app_version,
            "environment": settings.environment,
            "timestamp": datetime.now(UTC).isoformat(),
        }

    @app.get("/")
    async def root() -> dict:
        return {
            "name": settings.app_name,
            "version": settings.app_version,
            "docs": "/docs" if settings.debug else None,
        }

    return app


app = create_application()

