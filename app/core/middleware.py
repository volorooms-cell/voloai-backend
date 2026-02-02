"""Custom middleware for the application."""

import time
from collections.abc import Callable
from typing import Annotated

from fastapi import Depends, Request, Response
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint

import redis.asyncio as redis

from app.config import settings
from app.core.exceptions import RateLimitExceeded


class RateLimitMiddleware(BaseHTTPMiddleware):
    """Rate limiting middleware using Redis sliding window."""

    def __init__(
        self,
        app,
        requests_per_minute: int = 100,
        redis_url: str | None = None,
    ):
        """Initialize rate limiter.

        Args:
            app: FastAPI application
            requests_per_minute: Max requests per minute per IP
            redis_url: Redis connection URL
        """
        super().__init__(app)
        self.requests_per_minute = requests_per_minute
        self.redis_url = redis_url or settings.redis_url
        self._redis: redis.Redis | None = None

    async def get_redis(self) -> redis.Redis:
        """Get Redis connection."""
        if self._redis is None:
            self._redis = redis.from_url(
                self.redis_url,
                encoding="utf-8",
                decode_responses=True,
            )
        return self._redis

    def _get_client_ip(self, request: Request) -> str:
        """Extract client IP from request."""
        # Check for forwarded headers (behind proxy/load balancer)
        forwarded = request.headers.get("X-Forwarded-For")
        if forwarded:
            return forwarded.split(",")[0].strip()

        real_ip = request.headers.get("X-Real-IP")
        if real_ip:
            return real_ip

        return request.client.host if request.client else "unknown"

    async def dispatch(
        self,
        request: Request,
        call_next: RequestResponseEndpoint,
    ) -> Response:
        """Process request with rate limiting.

        Args:
            request: Incoming request
            call_next: Next middleware/route handler

        Returns:
            Response: Route response or rate limit error
        """
        # Skip rate limiting for health checks
        if request.url.path in ("/health", "/docs", "/redoc", "/openapi.json"):
            return await call_next(request)

        # Skip in debug mode if needed
        if settings.debug:
            return await call_next(request)

        try:
            redis_client = await self.get_redis()
            client_ip = self._get_client_ip(request)
            key = f"rate_limit:{client_ip}"
            current_time = int(time.time())
            window_start = current_time - 60  # 1 minute window

            # Use Redis pipeline for atomic operations
            async with redis_client.pipeline(transaction=True) as pipe:
                # Remove old entries
                await pipe.zremrangebyscore(key, 0, window_start)
                # Count current requests
                await pipe.zcard(key)
                # Add current request
                await pipe.zadd(key, {str(current_time): current_time})
                # Set expiry
                await pipe.expire(key, 60)
                results = await pipe.execute()

            request_count = results[1]

            # Check rate limit
            if request_count >= self.requests_per_minute:
                return JSONResponse(
                    status_code=429,
                    content={
                        "detail": "Too many requests. Please try again later.",
                        "retry_after": 60,
                    },
                    headers={
                        "Retry-After": "60",
                        "X-RateLimit-Limit": str(self.requests_per_minute),
                        "X-RateLimit-Remaining": "0",
                        "X-RateLimit-Reset": str(current_time + 60),
                    },
                )

            # Add rate limit headers to response
            response = await call_next(request)
            response.headers["X-RateLimit-Limit"] = str(self.requests_per_minute)
            response.headers["X-RateLimit-Remaining"] = str(
                max(0, self.requests_per_minute - request_count - 1)
            )
            response.headers["X-RateLimit-Reset"] = str(current_time + 60)
            return response

        except redis.RedisError:
            # If Redis is down, allow request through
            return await call_next(request)


class RequestLoggingMiddleware(BaseHTTPMiddleware):
    """Middleware for logging requests and response times."""

    async def dispatch(
        self,
        request: Request,
        call_next: RequestResponseEndpoint,
    ) -> Response:
        """Log request details and timing.

        Args:
            request: Incoming request
            call_next: Next middleware/route handler

        Returns:
            Response: Route response
        """
        start_time = time.time()

        # Add request ID
        request_id = request.headers.get("X-Request-ID") or str(time.time_ns())
        request.state.request_id = request_id

        # Process request
        response = await call_next(request)

        # Calculate duration
        duration = time.time() - start_time

        # Add timing headers
        response.headers["X-Request-ID"] = request_id
        response.headers["X-Response-Time"] = f"{duration:.3f}s"

        # Log if slow (> 1 second)
        if duration > 1.0 and settings.debug:
            print(
                f"SLOW REQUEST: {request.method} {request.url.path} "
                f"took {duration:.3f}s"
            )

        return response


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """Middleware to add security headers to responses."""

    async def dispatch(
        self,
        request: Request,
        call_next: RequestResponseEndpoint,
    ) -> Response:
        """Add security headers to response.

        Args:
            request: Incoming request
            call_next: Next middleware/route handler

        Returns:
            Response: Route response with security headers
        """
        response = await call_next(request)

        # Add security headers
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["X-XSS-Protection"] = "1; mode=block"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"

        if not settings.debug:
            response.headers["Strict-Transport-Security"] = (
                "max-age=31536000; includeSubDomains"
            )

        return response


# Rate limiter dependency for specific endpoints
class RateLimiter:
    """Rate limiter for specific endpoints using dependency injection."""

    def __init__(
        self,
        requests_per_minute: int = 10,
        key_prefix: str = "api",
    ):
        """Initialize rate limiter.

        Args:
            requests_per_minute: Max requests allowed
            key_prefix: Redis key prefix
        """
        self.requests_per_minute = requests_per_minute
        self.key_prefix = key_prefix
        self._redis: redis.Redis | None = None

    async def get_redis(self) -> redis.Redis:
        """Get Redis connection."""
        if self._redis is None:
            self._redis = redis.from_url(
                settings.redis_url,
                encoding="utf-8",
                decode_responses=True,
            )
        return self._redis

    async def __call__(self, request: Request) -> None:
        """Check rate limit for request.

        Args:
            request: Incoming request

        Raises:
            RateLimitExceeded: If rate limit exceeded
        """
        try:
            redis_client = await self.get_redis()

            # Get client identifier (IP or user ID if authenticated)
            client_id = request.client.host if request.client else "unknown"
            if hasattr(request.state, "user_id"):
                client_id = str(request.state.user_id)

            key = f"rate:{self.key_prefix}:{client_id}"
            current_time = int(time.time())
            window_start = current_time - 60

            async with redis_client.pipeline(transaction=True) as pipe:
                await pipe.zremrangebyscore(key, 0, window_start)
                await pipe.zcard(key)
                await pipe.zadd(key, {str(current_time): current_time})
                await pipe.expire(key, 60)
                results = await pipe.execute()

            if results[1] >= self.requests_per_minute:
                raise RateLimitExceeded()

        except redis.RedisError:
            # Allow request if Redis is unavailable
            pass


# Pre-configured rate limiters for different endpoints
login_limiter = RateLimiter(requests_per_minute=5, key_prefix="login")
register_limiter = RateLimiter(requests_per_minute=3, key_prefix="register")
password_reset_limiter = RateLimiter(requests_per_minute=3, key_prefix="password_reset")
booking_limiter = RateLimiter(requests_per_minute=10, key_prefix="booking")
message_limiter = RateLimiter(requests_per_minute=30, key_prefix="message")
