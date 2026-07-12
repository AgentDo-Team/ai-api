from typing import Generic, TypeVar

from pydantic import BaseModel

T = TypeVar("T")


class ApiResponse(BaseModel, Generic[T]):
    """모든 API 응답에서 공통으로 사용하는 응답 포맷."""

    success: bool
    message: str
    data: T | None = None

    @classmethod
    def ok(
        cls, data: T | None = None, message: str = "요청이 성공적으로 처리되었습니다."
    ) -> "ApiResponse[T]":
        return cls(success=True, message=message, data=data)

    @classmethod
    def fail(cls, message: str, data: T | None = None) -> "ApiResponse[T]":
        return cls(success=False, message=message, data=data)
