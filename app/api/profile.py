"""자사 프로필(입력폼) API 라우터.

로그인한 계정(회사) 기준으로 프로필을 조회/저장한다.
"""

from fastapi import APIRouter, Depends
from sqlmodel.ext.asyncio.session import AsyncSession

from app.api.auth import get_current_account
from app.db.models.company import Company
from app.db.session import get_session
from app.schemas.profile import ProfileRequest, ProfileResponse
from app.schemas.response import ApiResponse
from app.services import profile_service

router = APIRouter(prefix="/me", tags=["profile"])


@router.get("/profile")
async def get_my_profile(
    current_account: Company = Depends(get_current_account),
    session: AsyncSession = Depends(get_session),
) -> ApiResponse[ProfileResponse | None]:
    """내 회사의 자사 프로필을 조회한다. 아직 없으면 data=null."""
    profile = await profile_service.get_profile(session, current_account.id)
    data = (
        ProfileResponse.model_validate(profile, from_attributes=True)
        if profile is not None
        else None
    )
    return ApiResponse.ok(data=data)


@router.put("/profile")
async def upsert_my_profile(
    data: ProfileRequest,
    current_account: Company = Depends(get_current_account),
    session: AsyncSession = Depends(get_session),
) -> ApiResponse[ProfileResponse]:
    """내 회사의 자사 프로필을 저장한다 (없으면 생성, 있으면 갱신)."""
    profile = await profile_service.upsert_profile(
        session, current_account.id, data
    )
    return ApiResponse.ok(
        data=ProfileResponse.model_validate(profile, from_attributes=True),
        message="자사 프로필이 저장되었습니다.",
    )
