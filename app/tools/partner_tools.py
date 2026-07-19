from langchain_core.tools import tool

from app.db.repositories.company_repository import PartnerRepository
from app.db.repositories.search_set_repository import SearchSetRepository
from app.db.session import async_session_factory


@tool
async def list_partners(search_set_id: int) -> list:
    """
    search_set_id를 이용하여 해당 회사가 보유한 협력사 목록을 조회합니다.

    공고 분석의 약점(weakness)을 협력사가 해결해줄 수 있는지 판단할 때 사용합니다.
    반환: id(협력사 id), name, email(협업 제안 메일 수신자, 없으면 null),
    domain(사업 분야), tech_stack(보유 기술스택), description(상세 설명)
    """
    async with async_session_factory() as session:
        search_set = await SearchSetRepository(session).get(search_set_id)
        if not search_set:
            return []

        partners = await PartnerRepository(session).list_by_company(
            search_set.company_id, limit=100, offset=0
        )
        return [
            {
                "id": p.id,
                "name": p.name,
                "email": p.email,
                "domain": p.domain,
                "tech_stack": p.tech_stack,
                "description": p.description,
            }
            for p in partners
        ]
