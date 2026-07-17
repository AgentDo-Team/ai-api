"""분석 결과(analysis_results) 조회 API DTO.

3차 필터가 저장한 공고별 분석 결과를 프론트가 조회한다.
recommend_reason/weaknesses 는 3차 필터의 FitReason 리스트와 동일한 형태다.
"""

from __future__ import annotations

from pydantic import BaseModel, Field

from app.schemas.third_filter import FitReason


class AnalysisResultRead(BaseModel):
    """검색세트 내 공고 1건의 분석 결과."""

    bid_notice_id: int
    final_score: int | None = Field(
        default=None, description="최종점수(analysis_results.soft_score)"
    )
    recommend_reason: list[FitReason] = Field(
        default_factory=list, description="적합 판정 이유 목록"
    )
    weaknesses: list[FitReason] = Field(
        default_factory=list, description="부적합 판정 이유 목록"
    )
    summary: str | None = Field(default=None, description="공고 내용 100자 이내 요약")
    title: str = Field(description="공고 이름(bid_notices.title)")
    demand_org: str | None = Field(
        default=None, description="수요기관(bid_notices.demand_org)"
    )


class AnalysisResultsResponse(BaseModel):
    """검색세트의 분석 결과 목록. 최종점수 내림차순."""

    search_set_id: int
    results: list[AnalysisResultRead] = Field(default_factory=list)
