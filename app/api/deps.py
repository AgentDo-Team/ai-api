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
    return ThirdFilterService(session_factory=async_session_factory, llm=OpenAIProvider())
