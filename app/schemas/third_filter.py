"""3차 필터 API DTO.

요청: 2차 필터(하이브리드 검색) 결과 — 하드필터 통과 공고들과 공고별 상위 청크 매칭 목록.
응답: 최종점수(aggregate_score + soft_score) 상위 5개 공고의 채점/판정/요약 결과.

ChunkFitJudgment/FitJudgmentResult/NoticeSummaryResult 는 LLM structured output
타겟으로도 그대로 쓰인다(LLMProvider.complete_structured(response_model=...)).
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

# --------------------------------------------------------------------------- #
# 요청 DTO
# --------------------------------------------------------------------------- #


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


# --------------------------------------------------------------------------- #
# LLM structured output DTO
# --------------------------------------------------------------------------- #


class ChunkFitJudgment(BaseModel):
    """공고 청크 ↔ 회사 프로필/프로젝트 매칭 1건에 대한 적합/부적합 판정.

    verdict="fit" 인데 cited_source="none" 인 응답은 서비스 레이어가 unfit 으로
    강제 보정한다 (LLM 이 근거 없이 적합 판정을 지어내는 것을 방지).
    """

    chunk_id: int = Field(description="판정 대상 청크 ID")
    verdict: Literal["fit", "unfit"]
    cited_source: Literal["profile", "project", "none"] = Field(
        description="근거로 인용한 출처. 근거가 없으면 none"
    )
    cited_id: int | None = Field(default=None, description="인용한 프로필/프로젝트 ID")
    cited_field: str | None = Field(
        default=None, description="근거가 된 필드명(예: performance, tech_stack)"
    )
    reason: str = Field(description="판정 이유(한국어 1~2문장)")


class FitJudgmentResult(BaseModel):
    """공고 1건의 ranked_chunks 전체에 대한 일괄 판정 LLM 출력."""

    judgments: list[ChunkFitJudgment]


class NoticeSummaryResult(BaseModel):
    summary: str = Field(description="공고 핵심 내용 100자 이내 한국어 요약")


# --------------------------------------------------------------------------- #
# 응답 DTO
# --------------------------------------------------------------------------- #


class FitReason(BaseModel):
    """적합/부적합 판정 이유 1건. recommend_reason/weaknesses 는 이 항목의 리스트다."""

    chunk_id: int | None = Field(default=None, description="판정 대상 청크 ID(배점표 채점 실패 사유면 None)")
    reason: str = Field(description="판정 이유(한국어 1~2문장)")
    cited_source: Literal["profile", "project", "none"] = Field(
        description="근거로 인용한 출처. 근거가 없으면 none"
    )
    cited_id: int | None = Field(default=None, description="인용한 프로필/프로젝트 ID")
    cited_field: str | None = Field(
        default=None, description="근거가 된 필드명(예: performance, tech_stack)"
    )


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
