from __future__ import annotations

import time
from collections import defaultdict, deque
from collections.abc import Awaitable, Callable

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from agentic_engineering_network.shared.config import Settings


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next: Callable[[Request], Awaitable[Response]]) -> Response:
        response = await call_next(request)
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("X-Frame-Options", "DENY")
        response.headers.setdefault("Referrer-Policy", "no-referrer")
        response.headers.setdefault("Permissions-Policy", "camera=(), microphone=(), geolocation=()")
        return response


class RateLimitMiddleware(BaseHTTPMiddleware):
    def __init__(self, app, settings: Settings) -> None:
        super().__init__(app)
        self.settings = settings
        self.window_seconds = 60
        self.requests: dict[str, deque[float]] = defaultdict(deque)

    async def dispatch(self, request: Request, call_next: Callable[[Request], Awaitable[Response]]) -> Response:
        limit = max(1, self.settings.rate_limit_requests_per_minute)
        host = request.client.host if request.client else "unknown"
        key = f"{host}:{request.method}:{request.url.path}"
        now = time.monotonic()
        bucket = self.requests[key]
        while bucket and bucket[0] <= now - self.window_seconds:
            bucket.popleft()
        if len(bucket) >= limit:
            return JSONResponse({"detail": "Rate limit exceeded."}, status_code=429)
        bucket.append(now)
        return await call_next(request)


class OptionalAuthMiddleware(BaseHTTPMiddleware):
    PUBLIC_PREFIXES = ("/docs", "/openapi.json", "/api/health", "/api/readinessz")

    def __init__(self, app, settings: Settings) -> None:
        super().__init__(app)
        self.settings = settings

    async def dispatch(self, request: Request, call_next: Callable[[Request], Awaitable[Response]]) -> Response:
        if not self.settings.api_token or request.url.path.startswith(self.PUBLIC_PREFIXES):
            return await call_next(request)
        token = request.headers.get("x-aen-token", "")
        if token != self.settings.api_token:
            return JSONResponse({"detail": "Missing or invalid API token."}, status_code=401)
        if self.settings.admin_token and request.url.path.startswith("/api/settings"):
            admin_token = request.headers.get("x-aen-admin-token", "")
            role = request.headers.get("x-aen-role", "")
            if admin_token != self.settings.admin_token and role != "admin":
                return JSONResponse({"detail": "Admin role required."}, status_code=403)
        return await call_next(request)
