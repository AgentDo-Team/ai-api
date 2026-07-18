"""3차 필터 API DTO.

요청: 2차 필터(하이브리드 검색) 결과 — 하드필터 통과 공고들과 공고별 상위 청크 매칭 목록.
응답: 최종점수(aggregate_score + soft_score) 상위 5개 공고의 채점/판정/요약 결과.

FitReason/NoticeFitAnalysis/NoticeSummaryResult 는 LLM structured output 타겟으로도 그대로
쓰인다 (NoticeFitAnalysis 는 공고 1건당 1회 요청을 상위 5건 묶어 보내므로
LLMProvider.complete_structured_batch, NoticeSummaryResult 는 complete_structured 로 호출).
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


class FitReason(BaseModel):
    """공고 ↔ 회사 적합성 분석 항목 1건. recommend_reason/weaknesses 는 이 항목의 리스트다.

    LLM structured output 타겟이자 그대로 API 응답/DB(JSONB) 형태로도 쓰인다.

    grounding 이 근거의 강도를 나타낸다:
    - "cited": 프로필/프로젝트의 특정 필드를 인용해 뒷받침되는 항목. cited_source/cited_id/
      cited_field 가 실제 값을 가리킨다.
    - "inferred": 인용할 필드는 없지만 공고 요구사항과 회사 정보를 견줘 도출한 항목
      (예: "공고가 요구하는 클라우드 전환 실적이 프로필·프로젝트 어디에도 없음").
      근거 부재 자체가 관찰인 경우가 대부분이라 weaknesses 에서 특히 많이 나온다.

    grounding="cited" 인데 cited_source="none" 인 응답은 서비스 레이어가 "inferred" 로
    강제 보정한다 (LLM 이 인용 없이 인용한 척하는 것을 방지).
    """

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
    """공고 1건의 청크 전체 ↔ 회사 프로필/프로젝트 전체를 견준 적합성 분석 LLM 출력.

    청크별 fit/unfit 을 따로 묻지 않고 공고를 통째로 읽혀 추천사유/약점을 뽑는다.
    """

    recommend_reason: list[FitReason] = Field(
        description="이 공고에 참여할 만한 이유(최대 5개)"
    )
    weaknesses: list[FitReason] = Field(
        description="이 공고에서 불리하거나 부족한 점(최대 5개)"
    )


class NoticeSummaryResult(BaseModel):
    summary: str = Field(description="공고 핵심 내용 100자 이내 한국어 요약")


# --------------------------------------------------------------------------- #
# 응답 DTO
# --------------------------------------------------------------------------- #


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
