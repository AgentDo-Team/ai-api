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
    return (await get_profile(session, company_id)) is not None
