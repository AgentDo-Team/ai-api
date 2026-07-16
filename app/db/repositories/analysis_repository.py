"""분석 결과(analysis_result) 영속성 계층."""

from __future__ import annotations

from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.db.models.analysis import AnalysisResult
from app.db.models.bid import BidNotice


class AnalysisResultRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def add(self, analysis_result: AnalysisResult) -> AnalysisResult:
        self.session.add(analysis_result)
        await self.session.flush()
        return analysis_result

    async def list_by_search_set(
        self, search_set_id: int, limit: int = 5
    ) -> list[tuple[AnalysisResult, BidNotice]]:
        """검색세트의 분석 결과를 공고(title/demand_org)와 조인해 점수 내림차순 상위 N건 반환.

        soft_score 가 NULL 인 행은 정렬상 마지막으로 밀린다(nulls last).
        """
        result = await self.session.exec(
            select(AnalysisResult, BidNotice)
            .join(BidNotice, BidNotice.id == AnalysisResult.bid_notice_id)
            .where(AnalysisResult.search_set_id == search_set_id)
            .order_by(AnalysisResult.soft_score.desc().nullslast())
            .limit(limit)
        )
        return list(result.all())

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
