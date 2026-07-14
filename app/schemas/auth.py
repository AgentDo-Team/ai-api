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


class AccountResponse(BaseModel):
    """계정(=회사) 정보 응답 (비밀번호 해시는 노출하지 않는다).

    has_profile: 자사 프로필(입력폼)을 작성했는지 여부.
    프론트는 이 값으로 온보딩 화면 vs 채팅 화면을 분기한다.
    """

    id: int
    email: EmailStr
    name: str | None = None
    contact_name: str | None = None
    created_at: datetime
    has_profile: bool = False


class TokenResponse(BaseModel):
    """로그인 성공 시 발급되는 액세스 토큰 응답."""

    access_token: str
    token_type: str = "bearer"
