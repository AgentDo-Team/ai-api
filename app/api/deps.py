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
from app.db.session import async_session_factory, get_session
from app.llm.openai_provider import OpenAIProvider
from app.services.company_service import CompanyService
from app.services.third_filter_service import ThirdFilterService

SessionDep = Annotated[AsyncSession, Depends(get_session)]


def get_company_service(session: SessionDep) -> CompanyService:
    return CompanyService(
        session=session,
        company_repo=CompanyRepository(session),
        profile_repo=CompanyProfileRepository(session),
        project_repo=CompanyProjectRepository(session),
    )


def get_third_filter_service() -> ThirdFilterService:
    # 공고 간 병렬 처리를 위해 요청 세션 대신 세션 팩토리를 넘긴다
    # (서비스가 공고마다 독립 세션을 연다).
    return ThirdFilterService(session_factory=async_session_factory, llm=OpenAIProvider())
