from datetime import datetime

from pydantic import BaseModel, EmailStr, Field


class SignupRequest(BaseModel):
    """회원가입 요청 본문 (계정 = 회사).

    email/password 외에 companies 테이블의 기본 정보(회사명, 담당자 이름)를
    가입 시점에 함께 채울 수 있다. 나머지는 선택값.
    """

    email: EmailStr
    password: str = Field(min_length=8, max_length=72)  # bcrypt 입력 한계 72바이트
    name: str | None = Field(
        default=None, max_length=200, description="회사명", examples=["에이전트두"]
    )
    contact_name: str | None = Field(
        default=None, max_length=100, description="담당자 이름", examples=["김준혁"]
    )


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
    """로그인 성공 시 발급되는 액세스 토큰 응답.

    has_profile: 자사 프로필(입력폼)을 작성했는지 여부.
    프론트는 로그인 직후 이 값으로 온보딩(입력폼) 화면 vs 채팅 화면을 분기한다.
    """

    access_token: str
    token_type: str = "bearer"
    has_profile: bool = False
