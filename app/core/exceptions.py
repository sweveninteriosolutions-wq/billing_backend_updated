from fastapi import HTTPException
from app.constants.error_codes import ErrorCode


class AppException(HTTPException):
    def __init__(
        self,
        status_code: int,
        message: str,
        error_code: ErrorCode,
        details: dict | None = None,
    ):
        super().__init__(status_code=status_code, detail=message)
        self.error_code = error_code
        self.details = details
