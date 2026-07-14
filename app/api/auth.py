"""회원가입 / 로그인 API 라우터 (계정 = 회사)."""

import jwt
from fastapi import APIRouter, Depends
from fastapi.security import OAuth2PasswordBearer
from sqlmodel.ext.asyncio.session import AsyncSession

from app.common.exceptions import AppException
from app.core.security import decode_access_token
from app.db.models.company import Company
from app.db.session import get_session
from app.schemas.auth import (
    AccountResponse,
    LoginRequest,
    SignupRequest,
    TokenResponse,
)
from app.schemas.response import ApiResponse
from app.services import auth_service, profile_service

router = APIRouter(prefix="/auth", tags=["auth"])

# 로그인 엔드포인트에서 토큰을 발급받아 Authorization: Bearer <token> 로 전달
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/login")


@router.post("/signup")
async def signup(
    data: SignupRequest,
    session: AsyncSession = Depends(get_session),
) -> ApiResponse[AccountResponse]:
    company = await auth_service.signup(session, data)
    # 방금 가입한 계정은 아직 프로필이 없으므로 has_profile=False
    return ApiResponse.ok(
        data=AccountResponse.model_validate(company, from_attributes=True),
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


async def get_current_account(
    token: str = Depends(oauth2_scheme),
    session: AsyncSession = Depends(get_session),
) -> Company:
    """Bearer 토큰을 검증하고 현재 로그인한 계정(회사)을 반환하는 의존성."""
    credentials_error = AppException("인증 정보가 유효하지 않습니다.", status_code=401)
    try:
        payload = decode_access_token(token)
        account_id = payload.get("sub")
    except jwt.PyJWTError as exc:
        raise credentials_error from exc

    if account_id is None:
        raise credentials_error

    company = await session.get(Company, int(account_id))
    if company is None:
        raise credentials_error
    return company


@router.get("/me")
async def me(
    current_account: Company = Depends(get_current_account),
    session: AsyncSession = Depends(get_session),
) -> ApiResponse[AccountResponse]:
    """현재 로그인한 계정 정보 + 프로필 작성 여부(has_profile).

    프론트는 has_profile 로 온보딩(입력폼) 화면과 채팅 화면을 분기한다.
    """
    account = AccountResponse.model_validate(current_account, from_attributes=True)
    account.has_profile = await profile_service.has_profile(
        session, current_account.id
    )
    return ApiResponse.ok(data=account)
