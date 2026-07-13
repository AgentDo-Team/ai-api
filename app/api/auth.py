"""회원가입 / 로그인 API 라우터."""

import jwt
from fastapi import APIRouter, Depends
from fastapi.security import OAuth2PasswordBearer
from sqlmodel.ext.asyncio.session import AsyncSession

from app.common.exceptions import AppException
from app.core.security import decode_access_token
from app.db.models.user import User
from app.db.session import get_session
from app.schemas.auth import (
    LoginRequest,
    SignupRequest,
    TokenResponse,
    UserResponse,
)
from app.schemas.response import ApiResponse
from app.services import auth_service

router = APIRouter(prefix="/auth", tags=["auth"])

# 로그인 엔드포인트에서 토큰을 발급받아 Authorization: Bearer <token> 로 전달
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/login")


@router.post("/signup")
async def signup(
    data: SignupRequest,
    session: AsyncSession = Depends(get_session),
) -> ApiResponse[UserResponse]:
    user = await auth_service.signup(session, data)
    return ApiResponse.ok(
        data=UserResponse.model_validate(user, from_attributes=True),
        message="회원가입이 완료되었습니다.",
    )


@router.post("/login")
async def login(
    data: LoginRequest,
    session: AsyncSession = Depends(get_session),
) -> ApiResponse[TokenResponse]:
    access_token = await auth_service.login(session, data)
    return ApiResponse.ok(
        data=TokenResponse(access_token=access_token),
        message="로그인에 성공했습니다.",
    )


async def get_current_user(
    token: str = Depends(oauth2_scheme),
    session: AsyncSession = Depends(get_session),
) -> User:
    """Bearer 토큰을 검증하고 현재 로그인한 사용자를 반환하는 의존성."""
    credentials_error = AppException("인증 정보가 유효하지 않습니다.", status_code=401)
    try:
        payload = decode_access_token(token)
        user_id = payload.get("sub")
    except jwt.PyJWTError as exc:
        raise credentials_error from exc

    if user_id is None:
        raise credentials_error

    user = await session.get(User, int(user_id))
    if user is None:
        raise credentials_error
    return user


@router.get("/me")
async def me(
    current_user: User = Depends(get_current_user),
) -> ApiResponse[UserResponse]:
    """현재 로그인한 사용자 정보 조회 (인증 확인용)."""
    return ApiResponse.ok(
        data=UserResponse.model_validate(current_user, from_attributes=True),
    )
