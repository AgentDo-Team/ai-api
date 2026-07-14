"""자사 프로필(입력폼) 조회·저장 로직.

계정 = 회사이므로 프로필은 companies.id 기준으로 1:1 연결된다
(company_profiles.company_id UNIQUE).
"""

from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.db.models.company import CompanyProfile
from app.schemas.profile import ProfileRequest


async def get_profile(
    session: AsyncSession, company_id: int
) -> CompanyProfile | None:
    """회사의 자사 프로필을 반환한다. 없으면 None."""
    return await session.scalar(
        select(CompanyProfile).where(CompanyProfile.company_id == company_id)
    )


async def has_profile(session: AsyncSession, company_id: int) -> bool:
    """자사 프로필 작성 여부. 프론트의 온보딩/채팅 화면 분기 근거."""
    return (await get_profile(session, company_id)) is not None


async def upsert_profile(
    session: AsyncSession, company_id: int, data: ProfileRequest
) -> CompanyProfile:
    """자사 프로필을 저장한다. 없으면 생성, 있으면 갱신(upsert)."""
    profile = await get_profile(session, company_id)
    if profile is None:
        profile = CompanyProfile(company_id=company_id)
        session.add(profile)

    # 요청에 담긴 값으로 필드를 갱신 (모든 필드 선택값)
    profile.company_scale = data.company_scale
    profile.target_techs = data.target_techs
    profile.offered_solutions = data.offered_solutions
    profile.strengths_diff = data.strengths_diff
    profile.credit_rating = data.credit_rating
    profile.sp_grade = data.sp_grade

    await session.commit()
    await session.refresh(profile)
    return profile
