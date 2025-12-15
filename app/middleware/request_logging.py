import time
import logging
from fastapi import Request

logger = logging.getLogger("access")


async def request_logging_middleware(request: Request, call_next):
    start_time = time.perf_counter()

    response = await call_next(request)

    process_time = (time.perf_counter() - start_time) * 1000

    logger.info(
        "",
        extra={
            "client_addr": request.client.host if request.client else "unknown",
            "method": request.method,
            "path": request.url.path,
            "status_code": response.status_code,
            "process_time_ms": round(process_time, 2),
        },
    )

    return response
