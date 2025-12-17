# app/utils/response.py

from typing import TypeVar, Generic, Optional, Dict, Any
from pydantic import BaseModel

T = TypeVar("T")


def success_response(message: str, data: Optional[T] = None) -> Dict[str, Any]:
    return {
        "success": True,
        "message": message,
        "data": data,
    }


class APIResponse(BaseModel, Generic[T]):
    success: bool = True
    message: str
    data: Optional[T] = None