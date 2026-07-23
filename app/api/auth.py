import jwt
from fastapi import APIRouter, Depends
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
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
security = HTTPBearer(auto_error=False)


@router.post("/signup")
async def signup(
    data: SignupRequest,
    session: AsyncSession = Depends(get_session),
) -> ApiResponse[AccountResponse]:
    company = await auth_service.signup(session, data)
    return ApiResponse.ok(
        data=AccountResponse.model_validate(company, from_attributes=True),
        message="회원가입이 완료되었습니다.",
    )


@router.post("/login")
async def login(
    data: LoginRequest,
    session: AsyncSession = Depends(get_session),
) -> ApiResponse[TokenResponse]:
    access_token, company = await auth_service.login(session, data)
    has_profile = await profile_service.has_profile(session, company.id)
    return ApiResponse.ok(
        data=TokenResponse(access_token=access_token, has_profile=has_profile),
        message="로그인에 성공했습니다.",
    )


async def get_current_account(
    credentials: HTTPAuthorizationCredentials | None = Depends(security),
    session: AsyncSession = Depends(get_session),
) -> Company:
    """Bearer 토큰을 검증하고 현재 로그인한 계정(회사)을 반환하는 의존성."""
    credentials_error = AppException("인증 정보가 유효하지 않습니다.", status_code=401)
    if credentials is None:
        raise credentials_error
    try:
        payload = decode_access_token(credentials.credentials)
        account_id = payload.get("sub")
    except jwt.PyJWTError as exc:
        raise credentials_error from exc

    if account_id is None:
        raise credentials_error

    company = await session.get(Company, int(account_id))
    if company is None:
        raise credentials_error
    return company


@router.post("/logout")
async def logout(
    current_account: Company = Depends(get_current_account),
) -> ApiResponse[None]:
    return ApiResponse.ok(message="로그아웃되었습니다.")


@router.get("/me")
async def me(
    current_account: Company = Depends(get_current_account),
    session: AsyncSession = Depends(get_session),
) -> ApiResponse[AccountResponse]:
    account = AccountResponse.model_validate(current_account, from_attributes=True)
    account.has_profile = await profile_service.has_profile(
        session, current_account.id
    )
    return ApiResponse.ok(data=account)
