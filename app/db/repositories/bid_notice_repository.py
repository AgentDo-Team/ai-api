"""입찰공고(bid_notice) 영속성 계층."""

from __future__ import annotations

from sqlmodel.ext.asyncio.session import AsyncSession

from app.db.models.bid import BidNotice


class BidNoticeRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def add(self, bid_notice: BidNotice) -> BidNotice:
        self.session.add(bid_notice)
        await self.session.flush()
        return bid_notice

    async def get(self, bid_notice_id: int) -> BidNotice | None:
        return await self.session.get(BidNotice, bid_notice_id)

    async def delete(self, bid_notice: BidNotice) -> None:
        await self.session.delete(bid_notice)
