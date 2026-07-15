from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.db.models.bid import BidNotice, Chunk, ParseStatus

class BidNoticeRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def add(self, bid_notice: BidNotice) -> BidNotice:
        self.session.add(bid_notice)
        await self.session.flush()
        return bid_notice

    async def get_by_notice_no(self, notice_no: str) -> BidNotice | None:
        result = await self.session.exec(
            select(BidNotice).where(BidNotice.notice_no == notice_no)
        )
        return result.first()

    async def get_pending_notices(self) -> list[BidNotice]:
        result = await self.session.exec(
            select(BidNotice).where(BidNotice.parse_status == ParseStatus.PENDING)
        )
        return list(result.all())

    async def update_status(self, bid_notice_id: int, status: ParseStatus) -> None:
        notice = await self.session.get(BidNotice, bid_notice_id)
        if notice:
            notice.parse_status = status
            await self.session.flush()

class ChunkRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def add_all(self, chunks: list[Chunk]) -> None:
        self.session.add_all(chunks)
        await self.session.flush()