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
        company_id: int = None
    ) -> List[ProposalDraft]:
        """
        조건에 맞는 제안서 초안 목록을 최신순으로 조회합니다.
        """
        query = select(ProposalDraft)
        if company_id:
            query = query.where(ProposalDraft.company_id == company_id)
            
        # 최신 생성된 제안서가 먼저 오도록 정렬
        query = query.order_by(desc(ProposalDraft.created_at))
        
        result = await self.session.exec(query)
        return result.all()