"""라우터가 쓰는 의존성 조립.

테스트는 `app.dependency_overrides[get_company_service]` 하나만 갈아끼우면
DB 없이 전 엔드포인트를 검증할 수 있다.
"""

from typing import Annotated

from fastapi import Depends, Path
from sqlmodel.ext.asyncio.session import AsyncSession

from app.api.auth import get_current_account
from app.common.exceptions import AppException
from app.db.models.company import Company
from app.db.repositories.company_repository import (
    CompanyProfileRepository,
    CompanyProjectRepository,
    CompanyRepository,
    PartnerRepository,
)
from app.db.repositories.analysis_repository import AnalysisResultRepository
from app.db.repositories.chat_message_repository import ChatMessageRepository
from app.db.repositories.search_set_repository import SearchSetRepository
from app.db.session import async_session_factory, get_session
from app.llm.openai_provider import OpenAIProvider
from app.services.chat_service import ChatService
from app.services.collaboration_agent_service import CollaborationAgentService
from app.services.company_service import CompanyService
from app.services.third_filter_service import ThirdFilterService

SessionDep = Annotated[AsyncSession, Depends(get_session)]
CurrentAccountDep = Annotated[Company, Depends(get_current_account)]


async def verify_company_access(
    company_id: Annotated[int, Path(description="회사 ID", ge=1)],
    current_account: CurrentAccountDep,
) -> None:
    """경로의 company_id가 JWT 토큰의 계정(=회사) id와 일치하는지 검증한다.

    계정 = 회사 구조이므로, 본인 회사의 프로필/프로젝트만 접근할 수 있다.
    토큰 없음/무효 → 401 (get_current_account), 남의 회사 → 403.
    """
    if current_account.id != company_id:
        raise AppException("본인 회사의 리소스만 접근할 수 있습니다.", status_code=403)


def get_company_service(session: SessionDep) -> CompanyService:
    return CompanyService(
        session=session,
        company_repo=CompanyRepository(session),
        profile_repo=CompanyProfileRepository(session),
        project_repo=CompanyProjectRepository(session),
        partner_repo=PartnerRepository(session),
    )


def get_search_set_repository(session: SessionDep) -> SearchSetRepository:
    return SearchSetRepository(session)


def get_chat_service(session: SessionDep) -> ChatService:
    return ChatService(
        session=session,
        search_set_repo=SearchSetRepository(session),
        chat_message_repo=ChatMessageRepository(session),
    )


def get_collaboration_agent_service(session: SessionDep) -> CollaborationAgentService:
    return CollaborationAgentService(
        session=session,
        search_set_repo=SearchSetRepository(session),
        chat_message_repo=ChatMessageRepository(session),
    )


def get_analysis_repository(session: SessionDep) -> AnalysisResultRepository:
    return AnalysisResultRepository(session)


def get_third_filter_service() -> ThirdFilterService:
    # 공고 간 병렬 처리를 위해 요청 세션 대신 세션 팩토리를 넘긴다
    # (서비스가 공고마다 독립 세션을 연다).
    return ThirdFilterService(session_factory=async_session_factory, llm=OpenAIProvider())
