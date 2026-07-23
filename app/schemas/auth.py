from datetime import datetime

from pydantic import BaseModel, EmailStr, Field


class SignupRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=72)  
    name: str | None = Field(
        default=None, max_length=200, description="회사명", examples=["에이전트두"]
    )
    contact_name: str | None = Field(
        default=None, max_length=100, description="담당자 이름", examples=["김준혁"]
    )


class LoginRequest(BaseModel):

    email: EmailStr
    password: str


class AccountResponse(BaseModel):
    id: int
    email: EmailStr
    name: str | None = None
    contact_name: str | None = None
    created_at: datetime
    has_profile: bool = False


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    has_profile: bool = False
