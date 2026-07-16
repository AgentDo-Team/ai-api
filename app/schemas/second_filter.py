"""2차 소프트필터(하이브리드 검색) DTO.

하드필터 통과 공고들의 개요·요구사항 청크를 자사 프로필/프로젝트와 유사도 비교해
공고별 상위 매칭 청크(ranked_chunks)와 매칭도(aggregate_score)를 산출한다.

출력은 3차 필터(app/schemas/third_filter.py: ThirdFilterRequest)의 입력 shape과
정렬돼 있어, 그대로 다음 단계(POST /api/third-filter)로 넘길 수 있다.
(RankedChunk 는 third_filter 의 RankedChunkIn 필드를 모두 포함한 상위집합)
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class RankedChunk(BaseModel):
    """공고 청크 1건과 자사 프로필/프로젝트 매칭 결과."""

    chunk_id: int = Field(description="매칭된 공고 청크 ID", ge=1)
    rank: int = Field(description="공고 내 매칭 순위(1부터)", ge=1)
    score: float = Field(description="하이브리드(dense+BM25) RRF 융합 점수")
    matched_source: Literal["profile", "project"] = Field(
        description="매칭 근거가 회사 프로필인지 과거 프로젝트인지"
    )
    matched_id: int = Field(description="매칭된 프로필/프로젝트 ID", ge=1)
    # --- 3차 입력엔 없지만 참고/디버깅용으로 함께 내려주는 필드 (3차는 무시) ---
    l_topic: str | None = Field(default=None, description="청크 도메인(개요/요구사항)")
    preview: str | None = Field(default=None, description="청크 본문 앞부분 미리보기")


class NoticeSoftResult(BaseModel):
    """공고 1건의 2차 소프트필터 결과."""

    bid_notice_id: int = Field(description="입찰공고 ID", ge=1)
    aggregate_score: float = Field(description="공고 전체 매칭도(청크 점수 집계)")
    ranked_chunks: list[RankedChunk] = Field(
        default_factory=list, description="공고당 top-k 매칭 청크(순위순)"
    )


class SecondFilterResult(BaseModel):
    """2차 소프트필터 전체 결과. 3차 필터 요청(ThirdFilterRequest)으로 그대로 전달 가능."""

    search_set_id: int = Field(description="검색세트 ID")
    company_id: int = Field(description="회사 ID")
    results: list[NoticeSoftResult] = Field(
        default_factory=list, description="하드필터 통과 공고들의 매칭 결과(매칭도 내림차순)"
    )
