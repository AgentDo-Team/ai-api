from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class RankedChunkIn(BaseModel):
    chunk_id: int = Field(description="매칭된 공고 청크 ID", ge=1)
    rank: int = Field(description="공고 내 매칭 순위(1부터)", ge=1)
    score: float = Field(description="하이브리드(dense+BM25) 융합 점수")
    matched_source: Literal["profile", "project"] = Field(
        description="매칭 근거가 회사 프로필인지 과거 프로젝트인지"
    )
    matched_id: int = Field(description="매칭된 프로필/프로젝트 ID", ge=1)


class NoticeResultIn(BaseModel):
    bid_notice_id: int = Field(description="입찰공고 ID", ge=1)
    aggregate_score: float = Field(description="공고 전체 매칭도(청크 점수 집계)")
    ranked_chunks: list[RankedChunkIn] = Field(description="공고당 top-k 매칭 청크")


class ThirdFilterRequest(BaseModel):
    search_set_id: int = Field(description="검색세트 ID", ge=1)
    company_id: int = Field(description="회사 ID", ge=1)
    results: list[NoticeResultIn] = Field(min_length=1, description="하드필터 통과 공고들")


class FitReason(BaseModel):

    chunk_id: int | None = Field(
        default=None, description="근거가 된 공고 청크 ID(특정할 수 없으면 None)"
    )
    reason: str = Field(description="판정 이유(한국어 1~2문장)")
    grounding: Literal["cited", "inferred"] = Field(
        default="inferred",
        description="근거 강도. cited=프로필/프로젝트 필드 인용, inferred=정황 추론",
    )
    cited_source: Literal["profile", "project", "none"] = Field(
        description="근거로 인용한 출처. 인용할 근거가 없으면 none"
    )
    cited_id: int | None = Field(default=None, description="인용한 프로필/프로젝트 ID")
    cited_field: str | None = Field(
        default=None, description="근거가 된 필드명(예: performance, tech_stack)"
    )


class NoticeFitAnalysis(BaseModel):
    recommend_reason: list[FitReason] = Field(
        description="이 공고에 참여할 만한 이유(최대 5개)"
    )
    weaknesses: list[FitReason] = Field(
        description="이 공고에서 불리하거나 부족한 점(최대 5개)"
    )


class NoticeSummaryResult(BaseModel):
    summary: str = Field(description="공고 핵심 내용 100자 이내 한국어 요약")


class ThirdFilterNoticeRead(BaseModel):
    bid_notice_id: int
    final_score: int = Field(
        description="최종점수(배점표 기반 채점 점수). aggregate_score 는 반영하지 않는다."
    )
    aggregate_score: float = Field(
        description="2차 필터가 산출한 공고 매칭도(참고용). 최종점수/정렬에는 반영되지 않는다."
    )
    recommend_reason: list[FitReason] = Field(default_factory=list, description="적합 판정 이유 목록")
    weaknesses: list[FitReason] = Field(default_factory=list, description="부적합 판정 이유 목록")
    summary: str | None = Field(default=None, description="공고 내용 100자 이내 요약")
    title: str = Field(description="공고 이름(bid_notices.title)")
    demand_org: str | None = Field(default=None, description="발주처(bid_notices.demand_org)")


class SkippedNotice(BaseModel):
    bid_notice_id: int
    reason: str = Field(description="처리에서 제외된 사유")


class ThirdFilterResponse(BaseModel):
    results: list[ThirdFilterNoticeRead] = Field(
        description="최종점수 내림차순 상위 5개 공고"
    )
    skipped: list[SkippedNotice] = Field(
        default_factory=list, description="예외로 처리에서 제외된 공고들"
    )
