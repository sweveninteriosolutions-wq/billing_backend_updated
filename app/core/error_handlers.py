from fastapi import Request
from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError
from sqlalchemy.exc import IntegrityError
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.constants.error_codes import ErrorCode
from app.core.exceptions import AppException
import logging

logger = logging.getLogger(__name__)


# -------------------------
# APP EXCEPTIONS
# -------------------------
async def app_exception_handler(request: Request, exc: AppException):
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "success": False,
            "message": exc.detail,
            "error_code": exc.error_code,
            "details": exc.details,
        },
    )


# -------------------------
# FASTAPI VALIDATION
# -------------------------
async def validation_exception_handler(
    request: Request, exc: RequestValidationError
):
    return JSONResponse(
        status_code=422,
        content={
            "success": False,
            "message": "Invalid request data",
            "error_code": ErrorCode.VALIDATION_ERROR,
            "details": exc.errors(),
        },
    )


# -------------------------
# HTTP EXCEPTIONS (mapped)
# -------------------------
HTTP_STATUS_TO_ERROR_CODE = {
    400: ErrorCode.VALIDATION_ERROR,
    401: ErrorCode.UNAUTHORIZED,
    403: ErrorCode.PERMISSION_DENIED,
    404: ErrorCode.NOT_FOUND,
    409: ErrorCode.CONFLICT,
    422: ErrorCode.VALIDATION_ERROR,
}


async def http_exception_handler(
    request: Request, exc: StarletteHTTPException
):
    error_code = HTTP_STATUS_TO_ERROR_CODE.get(
        exc.status_code,
        ErrorCode.INTERNAL_ERROR,
    )

    return JSONResponse(
        status_code=exc.status_code,
        content={
            "success": False,
            "message": exc.detail,
            "error_code": error_code,
            "details": None,
        },
    )


# -------------------------
# DB INTEGRITY ERRORS
# -------------------------
async def integrity_error_handler(
    request: Request, exc: IntegrityError
):
    logger.exception("DB Integrity error")

    return JSONResponse(
        status_code=409,
        content={
            "success": False,
            "message": "Database constraint violation",
            "error_code": ErrorCode.CONFLICT,
            "details": None,
        },
    )


# -------------------------
# LAST RESORT
# -------------------------
async def unhandled_exception_handler(request: Request, exc: Exception):
    logger.exception(
        "Unhandled exception",
        extra={
            "path": request.url.path,
            "method": request.method,
        },
    )

    return JSONResponse(
        status_code=500,
        content={
            "success": False,
            "message": "Something went wrong. Please try again.",
            "error_code": ErrorCode.INTERNAL_ERROR,
            "details": None,
        },
    )
