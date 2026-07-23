from langchain_core.tools import tool
from app.db.session import async_session_factory
from app.db.repositories.company_repository import CompanyRepository, CompanyProjectRepository
from app.db.repositories.bid_respository import BidNoticeRepository
from app.db.repositories.search_set_repository import SearchSetRepository

@tool
async def get_company_profile(search_set_id: int) -> dict:
    async with async_session_factory() as session:
        search_set_repo = SearchSetRepository(session)
        company_repo = CompanyRepository(session)
        
        search_set = await search_set_repo.get(search_set_id)
        if not search_set:
            return {"error": "SearchSet을 찾을 수 없습니다."}
            
        company = await company_repo.get(search_set.company_id)
        if not company:
            return {"error": "회사를 찾을 수 없습니다."}
            
        return {
            "company_scale": getattr(company, "company_scale", ""),
            "target_techs": getattr(company, "target_techs", ""),
            "offered_solutions": getattr(company, "offered_solutions", ""),
            "strengths_diff": getattr(company, "strengths_diff", "")
        }

@tool
async def get_company_projects(search_set_id: int) -> list:
    
    async with async_session_factory() as session:
        search_set_repo = SearchSetRepository(session)
        project_repo = CompanyProjectRepository(session)
        
        search_set = await search_set_repo.get(search_set_id)
        if not search_set:
            return []
            
        projects = await project_repo.get_by_company_id(search_set.company_id)
        return [
            {
                "title": getattr(p, "title", ""),
                "client": getattr(p, "client", ""),
                "field": getattr(p, "field", ""),
                "tech_stack": getattr(p, "tech_stack", ""),
                "develop_features": getattr(p, "develop_features", ""),
                "performance": getattr(p, "performance", "")
            } for p in projects
        ]

@tool
async def get_bid_notice(bid_notice_id: int) -> dict:
    
    async with async_session_factory() as session:
        bid_repo = BidNoticeRepository(session)
        bid = await bid_repo.get(bid_notice_id)
        
        if not bid:
            return {"error": "공고를 찾을 수 없습니다."}
            
        return {
            "title": getattr(bid, "title", ""),
            "demand_org": getattr(bid, "demand_org", ""),
            "budget": getattr(bid, "budget", ""),
            "summary": getattr(bid, "summary", "")
        }