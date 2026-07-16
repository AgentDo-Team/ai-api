"""자사 프로필 조회 로직.

계정 = 회사이므로 프로필은 companies.id 기준으로 1:1 연결된다
(company_profiles.company_id UNIQUE).

프로필 CRUD 는 /api/companies/{company_id}/profile (CompanyService) 가 담당한다.
여기는 /auth/me 의 has_profile 판단에 필요한 조회만 남긴다.
"""

from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.db.models.company import CompanyProfile


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
