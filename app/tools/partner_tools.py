from langchain_core.tools import tool

from app.db.repositories.company_repository import PartnerRepository
from app.db.repositories.search_set_repository import SearchSetRepository
from app.db.session import async_session_factory


@tool
async def list_partners(search_set_id: int) -> list:
 
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
