from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.db.models.bid import BidNotice, ParseStatus

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
    async def get_chunked_notices(self) -> list[BidNotice]:
        """
        청크 분할은 완료되었으나(CHUNKED), 
        아직 임베딩이 완료되지 않은 공고 목록을 조회합니다.
        """
        stmt = select(BidNotice).where(BidNotice.parse_status == ParseStatus.CHUNKED)
        result = await self.session.exec(stmt)
        
        return list(result.all())