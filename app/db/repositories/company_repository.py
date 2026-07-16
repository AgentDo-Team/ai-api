"""회사 도메인 영속성 계층.

DB 접근만 담당한다. 존재 여부 판단·중복 처리·임베딩 같은 비즈니스 판단과 commit 은
서비스(app/services/company_service.py)의 몫이다.
"""

from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.db.models.company import Company, CompanyProfile, CompanyProject


class CompanyRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def add(self, company: Company) -> Company:
        self.session.add(company)
        await self.session.flush()  # id 채우기 (commit 은 서비스에서)
        return company

    async def get(self, company_id: int) -> Company | None:
        return await self.session.get(Company, company_id)

    async def get_by_email(self, email: str) -> Company | None:
        result = await self.session.exec(select(Company).where(Company.email == email))
        return result.first()

    async def delete(self, company: Company) -> None:
        await self.session.delete(company)


class CompanyProfileRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def add(self, profile: CompanyProfile) -> CompanyProfile:
        self.session.add(profile)
        await self.session.flush()
        return profile

    async def get_by_company_id(self, company_id: int) -> CompanyProfile | None:
        """프로필은 회사당 1개(company_id UNIQUE)라 조회 키가 company_id 다."""
        result = await self.session.exec(
            select(CompanyProfile).where(CompanyProfile.company_id == company_id)
        )
        return result.first()

    async def delete(self, profile: CompanyProfile) -> None:
        await self.session.delete(profile)


class CompanyProjectRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def add(self, project: CompanyProject) -> CompanyProject:
        self.session.add(project)
        await self.session.flush()
        return project

    async def get(self, project_id: int) -> CompanyProject | None:
        return await self.session.get(CompanyProject, project_id)

    async def list_by_company(
        self, company_id: int, limit: int = 20, offset: int = 0
    ) -> list[CompanyProject]:
        result = await self.session.exec(
            select(CompanyProject)
            .where(CompanyProject.company_id == company_id)
            .order_by(CompanyProject.id)
            .offset(offset)
            .limit(limit)
        )
        return list(result.all())

    async def delete(self, project: CompanyProject) -> None:
        await self.session.delete(project)
