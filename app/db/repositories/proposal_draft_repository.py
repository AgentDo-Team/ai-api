from sqlmodel import select
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