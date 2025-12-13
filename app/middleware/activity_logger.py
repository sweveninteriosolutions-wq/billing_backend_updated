from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.db import AsyncSessionLocal
from app.utils.activity_helpers import log_user_activity


class ActivityLoggerMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        response = await call_next(request)

        # Only log mutating requests
        if request.method not in {"POST", "PUT", "DELETE"}:
            return response

        user = getattr(request.state, "user", None)
        if not user:
            return response  # unauthenticated action → ignore

        message = f"{request.method} {request.url.path}"

        # Allow endpoint to override message
        custom_message = getattr(response, "activity_message", None)
        if custom_message:
            message = custom_message

        # 🔴 NEW SESSION — never reuse request DB session
        async with AsyncSessionLocal() as db:
            try:
                await log_user_activity(
                    db,
                    user_id=user.id,
                    username=user.username,
                    message=message,
                )
            except Exception as e:
                            # NEVER break request flow, but log the error for debugging.
                import logging
                logger = logging.getLogger(__name__)
                logger.error(f"Failed to log user activity: {e}", exc_info=True)
                pass

        return response
