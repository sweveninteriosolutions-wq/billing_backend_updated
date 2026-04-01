# app/middleware/rate_limiter.py
"""
Simple in-process sliding-window rate limiter per IP.

⚠️  PRODUCTION WARNING (ERP-006):
    This implementation uses in-memory dictionaries. In any deployment with
    more than one worker process (gunicorn multi-worker, Kubernetes multiple
    pods), each worker has its own independent counter — the effective rate
    limit becomes (AUTH_MAX_REQUESTS × number_of_workers).

    For production multi-worker deployments, replace this with a Redis-backed
    solution such as `slowapi` with a Redis store:
        https://slowapi.readthedocs.io/en/latest/

    The startup check in main.py will emit a WARNING log if APP_ENV=production
    and REDIS_URL is not set, to remind operators of this limitation.
"""

import time
import logging
import os
from collections import defaultdict, deque
from fastapi import Request, status
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

logger = logging.getLogger(__name__)

# Endpoints that get strict rate limiting
AUTH_PATHS = {"/auth/login", "/auth/refresh", "/auth/logout"}
AUTH_MAX_REQUESTS = 10     # per window
AUTH_WINDOW_SECONDS = 60

GLOBAL_MAX_REQUESTS = 300   # per window
GLOBAL_WINDOW_SECONDS = 60


class RateLimitMiddleware(BaseHTTPMiddleware):
    def __init__(self, app):
        super().__init__(app)
        # {ip: deque of timestamps}
        self._auth_buckets: dict[str, deque] = defaultdict(deque)
        self._global_buckets: dict[str, deque] = defaultdict(deque)

        # ERP-006: warn loudly in production without Redis
        app_env = os.getenv("APP_ENV", "development")
        redis_url = os.getenv("REDIS_URL", "")
        if app_env == "production" and not redis_url:
            logger.warning(
                "SECURITY WARNING (ERP-006): In-memory rate limiter is active in "
                "production without Redis. Rate limits are NOT shared across workers. "
                "Set REDIS_URL and switch to slowapi+Redis for production deployments."
            )

    def _is_rate_limited(
        self,
        buckets: dict,
        key: str,
        max_requests: int,
        window: int,
    ) -> bool:
        now = time.monotonic()
        dq = buckets[key]

        # Evict old entries
        while dq and dq[0] < now - window:
            dq.popleft()

        if len(dq) >= max_requests:
            return True

        dq.append(now)
        return False

    async def dispatch(self, request: Request, call_next):
        client_ip = request.client.host if request.client else "unknown"
        path = request.url.path

        # --- Auth-specific strict limit ---
        if path in AUTH_PATHS:
            if self._is_rate_limited(
                self._auth_buckets, client_ip,
                AUTH_MAX_REQUESTS, AUTH_WINDOW_SECONDS
            ):
                logger.warning(
                    "Auth rate limit hit",
                    extra={"ip": client_ip, "path": path}
                )
                return JSONResponse(
                    status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                    content={
                        "success": False,
                        "message": "Too many requests. Please wait before retrying.",
                        "error_code": "RATE_LIMIT_EXCEEDED",
                        "details": None,
                    },
                    headers={"Retry-After": str(AUTH_WINDOW_SECONDS)},
                )

        # --- Global per-IP limit ---
        if self._is_rate_limited(
            self._global_buckets, client_ip,
            GLOBAL_MAX_REQUESTS, GLOBAL_WINDOW_SECONDS
        ):
            logger.warning(
                "Global rate limit hit",
                extra={"ip": client_ip, "path": path}
            )
            return JSONResponse(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                content={
                    "success": False,
                    "message": "Too many requests. Please slow down.",
                    "error_code": "RATE_LIMIT_EXCEEDED",
                    "details": None,
                },
                headers={"Retry-After": str(GLOBAL_WINDOW_SECONDS)},
            )

        return await call_next(request)
