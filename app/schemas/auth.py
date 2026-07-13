from datetime import datetime

from pydantic import BaseModel, EmailStr, Field


class SignupRequest(BaseModel):
    """회원가입 요청 본문."""

    email: EmailStr
    password: str = Field(min_length=8, max_length=72)  # bcrypt 입력 한계 72바이트


class LoginRequest(BaseModel):
    """로그인 요청 본문."""

    email: EmailStr
    password: str


class UserResponse(BaseModel):
    """사용자 정보 응답 (비밀번호 해시는 노출하지 않는다)."""

    id: int
    email: EmailStr
    created_at: datetime


class TokenResponse(BaseModel):
    """로그인 성공 시 발급되는 액세스 토큰 응답."""

    access_token: str
    token_type: str = "bearer"
