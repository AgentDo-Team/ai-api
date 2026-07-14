"""라우터가 쓰는 의존성 조립.

테스트는 `app.dependency_overrides[get_company_service]` 하나만 갈아끼우면
DB 없이 전 엔드포인트를 검증할 수 있다.
"""

from typing import Annotated

from fastapi import Depends
from sqlmodel.ext.asyncio.session import AsyncSession

from app.db.repositories.company_repository import (
    CompanyProfileRepository,
    CompanyProjectRepository,
    CompanyRepository,
)
from app.db.session import get_session
from app.services.company_service import CompanyService

SessionDep = Annotated[AsyncSession, Depends(get_session)]


def get_company_service(session: SessionDep) -> CompanyService:
    return CompanyService(
        session=session,
        company_repo=CompanyRepository(session),
        profile_repo=CompanyProfileRepository(session),
        project_repo=CompanyProjectRepository(session),
    )
