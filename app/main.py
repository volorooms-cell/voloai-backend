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
from app.database import close_db, init_db

# Background task handle
_health_check_task: asyncio.Task | None = None


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Application lifespan events."""
    global _health_check_task

    # Startup
    if settings.debug:
        await init_db()

    # Run startup health check (non-blocking)
    asyncio.create_task(run_startup_health_check())

    # Start 24-hour health check scheduler
    _health_check_task = asyncio.create_task(start_health_check_scheduler())

    yield

    # Shutdown
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
        docs_url="/docs" if settings.debug else None,
        redoc_url="/redoc" if settings.debug else None,
        openapi_url="/openapi.json" if settings.debug else None,
        lifespan=lifespan,
    )

    # Exception handlers
    @app.exception_handler(AppException)
    async def app_exception_handler(request: Request, exc: AppException) -> JSONResponse:
        """Handle custom application exceptions."""
        return JSONResponse(
            status_code=exc.status_code,
            content={"detail": exc.detail},
            headers=exc.headers,
        )

    # Middleware (order matters - first added = last executed)
    # 1. Security headers (outermost)
    app.add_middleware(SecurityHeadersMiddleware)

    # 2. Rate limiting (production only)
    if settings.environment != "development":
        app.add_middleware(
            RateLimitMiddleware,
            requests_per_minute=settings.rate_limit_per_minute,
        )

    # 3. Request logging
    app.add_middleware(RequestLoggingMiddleware)

    # 4. CORS
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # 5. Gzip compression (innermost)
    app.add_middleware(GZipMiddleware, minimum_size=1000)

    # Include API routes
    app.include_router(api_router, prefix=settings.api_prefix)

    @app.get("/health")
    async def health_check() -> dict:
        """Health check endpoint."""
        return {
            "status": "healthy",
            "version": settings.app_version,
            "environment": settings.environment,
            "timestamp": datetime.now(UTC).isoformat(),
        }

    @app.get("/")
    async def root() -> dict:
        """Root endpoint."""
        return {
            "name": settings.app_name,
            "version": settings.app_version,
            "docs": "/docs" if settings.debug else None,
        }

    return app


app = create_application()


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "app.main:app",
        host=settings.host,
        port=settings.port,
        reload=settings.debug,
        workers=1 if settings.debug else settings.workers,
    )
