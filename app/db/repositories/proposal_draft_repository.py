from typing import List

from sqlmodel import select, desc
from sqlmodel.ext.asyncio.session import AsyncSession

from app.db.models.proposal_drafts import ProposalDraft

class ProposalDraftRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def add(self, proposal_draft: ProposalDraft) -> ProposalDraft:
        self.session.add(proposal_draft)
        await self.session.flush()
        return proposal_draft
    
    async def get_by_proposal_draft_id(self, proposal_draft_id: str) -> ProposalDraft | None:
        result = await self.session.exec(
            select(ProposalDraft).where(ProposalDraft.id == proposal_draft_id)
        )
        return result.first()
    
    async def get_list(
        self, 
        company_id: int = None, 
        search_set_id: int = None, 
        bid_notice_id: int = None
    ) -> List[ProposalDraft]:
        
        query = select(ProposalDraft)

        if company_id:
            query = query.where(ProposalDraft.company_id == company_id)
        if search_set_id:
            query = query.where(ProposalDraft.search_set_id == search_set_id)
        if bid_notice_id:
            query = query.where(ProposalDraft.bid_notice_id == bid_notice_id)
            
        query = query.order_by(desc(ProposalDraft.created_at))
        
        result = await self.session.exec(query)
        return result.all()