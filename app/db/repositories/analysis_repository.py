"""분석 결과(analysis_result) 영속성 계층."""

from __future__ import annotations

from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.db.models.analysis import AnalysisResult


class AnalysisResultRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def add(self, analysis_result: AnalysisResult) -> AnalysisResult:
        self.session.add(analysis_result)
        await self.session.flush()
        return analysis_result

    async def get_by_search_set_and_notice(
        self, search_set_id: int, bid_notice_id: int
    ) -> AnalysisResult | None:
        result = await self.session.exec(
            select(AnalysisResult).where(
                AnalysisResult.search_set_id == search_set_id,
                AnalysisResult.bid_notice_id == bid_notice_id,
            )
        )
        return result.first()
