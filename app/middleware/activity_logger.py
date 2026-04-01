# app/middleware/activity_logger.py
# ERP-025 FIXED: Registered in main.py (see main.py changes).
# ERP-050 FIXED: Logger imported at module level, not inside except block.

import logging
from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware
from app.core.db import AsyncSessionLocal
from app.utils.activity_helpers import emit_activity

logger = logging.getLogger(__name__)


class ActivityLoggerMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        response = await call_next(request)

        # Only log mutating requests
        if request.method not in {"POST", "PUT", "DELETE", "PATCH"}:
            return response

        user = getattr(request.state, "user", None)
        if not user:
            return response  # unauthenticated action → ignore

        message = f"{request.method} {request.url.path}"

        # Allow endpoint to override message
        custom_message = getattr(response, "activity_message", None)
        if custom_message:
            message = custom_message

        # NEW SESSION — never reuse request DB session
        async with AsyncSessionLocal() as db:
            try:
                await emit_activity(
                    db,
                    user_id=user.id,
                    username=user.username,
                    message=message,
                )
            except Exception:
                # NEVER break request flow, but log the error for debugging.
                logger.error(
                    "ActivityLoggerMiddleware: failed to log user activity",
                    extra={"user_id": user.id, "path": request.url.path},
                    exc_info=True,
                )

        return response
