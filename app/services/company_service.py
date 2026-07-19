"""회사 도메인 비즈니스 로직.

CRUD 단계에서는 임베딩하지 않는다. profile/project 의 embedding 컬럼은 계속 NULL 로 남고,
나중에 추천 단계에서 채운다(NULL = 미임베딩).
"""

from app.common.exceptions import AppException
from app.db.models.company import Company, CompanyProfile, CompanyProject, Partner
from app.db.repositories.company_repository import (
    CompanyProfileRepository,
    CompanyProjectRepository,
    CompanyRepository,
    PartnerRepository,
)
from app.schemas.company import (
    CompanyProfileCreate,
    CompanyProfileUpdate,
    CompanyProjectCreate,
    CompanyProjectUpdate,
    CompanyUpdate,
)
from app.schemas.partner import PartnerCreate, PartnerUpdate


class CompanyService:
    def __init__(
        self,
        session,
        company_repo: CompanyRepository,
        profile_repo: CompanyProfileRepository,
        project_repo: CompanyProjectRepository,
        partner_repo: PartnerRepository,
    ) -> None:
        self.session = session
        self.company_repo = company_repo
        self.profile_repo = profile_repo
        self.project_repo = project_repo
        self.partner_repo = partner_repo

    # ------------------------------------------------------------------ #
    # Company
    # ------------------------------------------------------------------ #

    async def get_company(self, company_id: int) -> Company:
        company = await self.company_repo.get(company_id)
        if company is None:
            raise AppException("회사를 찾을 수 없습니다.", status_code=404)
        return company

    async def update_company(self, company_id: int, data: CompanyUpdate) -> Company:
        company = await self.get_company(company_id)
        changes = data.model_dump(exclude_unset=True)

        email = changes.get("email")
        if email and email != company.email:
            existing = await self.company_repo.get_by_email(email)
            if existing and existing.id != company_id:
                raise AppException("이미 등록된 이메일입니다.", status_code=409)

        for key, value in changes.items():
            setattr(company, key, value)

        await self.company_repo.add(company)
        await self.session.commit()
        return company

    async def delete_company(self, company_id: int) -> None:
        """프로필/프로젝트는 FK ON DELETE CASCADE 로 함께 삭제된다."""
        company = await self.get_company(company_id)
        await self.company_repo.delete(company)
        await self.session.commit()

    # ------------------------------------------------------------------ #
    # CompanyProfile (회사당 1개)
    # ------------------------------------------------------------------ #

    async def create_profile(
        self, company_id: int, data: CompanyProfileCreate
    ) -> CompanyProfile:
        await self.get_company(company_id)  # 404

        if await self.profile_repo.get_by_company_id(company_id):
            raise AppException(
                "이미 프로필이 존재합니다. 수정하려면 PATCH를 사용하세요.", status_code=409
            )

        profile = CompanyProfile(company_id=company_id, **data.model_dump())

        await self.profile_repo.add(profile)
        await self.session.commit()
        return profile

    async def get_profile(self, company_id: int) -> CompanyProfile:
        await self.get_company(company_id)
        profile = await self.profile_repo.get_by_company_id(company_id)
        if profile is None:
            raise AppException("회사 프로필을 찾을 수 없습니다.", status_code=404)
        return profile

    async def update_profile(
        self, company_id: int, data: CompanyProfileUpdate
    ) -> CompanyProfile:
        profile = await self.get_profile(company_id)
        changes = data.model_dump(exclude_unset=True)

        for key, value in changes.items():
            setattr(profile, key, value)

        await self.profile_repo.add(profile)
        await self.session.commit()
        # updated_at 은 onupdate=now() 라 UPDATE 후 값이 무효화된다.
        # refresh 없이 읽으면 lazy load 가 걸려 async 컨텍스트 밖에서 IO 를 시도한다(MissingGreenlet).
        await self.session.refresh(profile)
        return profile

    async def delete_profile(self, company_id: int) -> None:
        profile = await self.get_profile(company_id)
        await self.profile_repo.delete(profile)
        await self.session.commit()

    # ------------------------------------------------------------------ #
    # CompanyProject (회사당 N개)
    # ------------------------------------------------------------------ #

    async def create_project(
        self, company_id: int, data: CompanyProjectCreate
    ) -> CompanyProject:
        await self.get_company(company_id)

        project = CompanyProject(company_id=company_id, **data.model_dump())

        await self.project_repo.add(project)
        await self.session.commit()
        return project

    async def list_projects(
        self, company_id: int, limit: int, offset: int
    ) -> list[CompanyProject]:
        await self.get_company(company_id)
        return await self.project_repo.list_by_company(
            company_id, limit=limit, offset=offset
        )

    async def get_project(self, company_id: int, project_id: int) -> CompanyProject:
        await self.get_company(company_id)
        project = await self.project_repo.get(project_id)
        # 다른 회사의 프로젝트는 존재하지 않는 것으로 취급한다.
        if project is None or project.company_id != company_id:
            raise AppException("프로젝트를 찾을 수 없습니다.", status_code=404)
        return project

    async def update_project(
        self, company_id: int, project_id: int, data: CompanyProjectUpdate
    ) -> CompanyProject:
        project = await self.get_project(company_id, project_id)
        changes = data.model_dump(exclude_unset=True)

        for key, value in changes.items():
            setattr(project, key, value)

        await self.project_repo.add(project)
        await self.session.commit()
        return project

    async def delete_project(self, company_id: int, project_id: int) -> None:
        project = await self.get_project(company_id, project_id)
        await self.project_repo.delete(project)
        await self.session.commit()

    # ------------------------------------------------------------------ #
    # Partner (회사당 N개)
    # ------------------------------------------------------------------ #

    async def create_partner(self, company_id: int, data: PartnerCreate) -> Partner:
        await self.get_company(company_id)

        partner = Partner(company_id=company_id, **data.model_dump())

        await self.partner_repo.add(partner)
        await self.session.commit()
        return partner

    async def list_partners(
        self, company_id: int, limit: int, offset: int
    ) -> list[Partner]:
        await self.get_company(company_id)
        return await self.partner_repo.list_by_company(
            company_id, limit=limit, offset=offset
        )

    async def get_partner(self, company_id: int, partner_id: int) -> Partner:
        await self.get_company(company_id)
        partner = await self.partner_repo.get(partner_id)
        # 다른 회사의 협력사는 존재하지 않는 것으로 취급한다.
        if partner is None or partner.company_id != company_id:
            raise AppException("협력사를 찾을 수 없습니다.", status_code=404)
        return partner

    async def update_partner(
        self, company_id: int, partner_id: int, data: PartnerUpdate
    ) -> Partner:
        partner = await self.get_partner(company_id, partner_id)
        changes = data.model_dump(exclude_unset=True)

        for key, value in changes.items():
            setattr(partner, key, value)

        await self.partner_repo.add(partner)
        await self.session.commit()
        return partner

    async def delete_partner(self, company_id: int, partner_id: int) -> None:
        partner = await self.get_partner(company_id, partner_id)
        await self.partner_repo.delete(partner)
        await self.session.commit()
