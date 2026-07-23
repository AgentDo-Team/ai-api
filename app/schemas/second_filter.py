from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class RankedChunk(BaseModel):

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

    bid_notice_id: int = Field(description="입찰공고 ID", ge=1)
    aggregate_score: float = Field(description="공고 전체 매칭도(청크 점수 집계)")
    ranked_chunks: list[RankedChunk] = Field(
        default_factory=list, description="공고당 top-k 매칭 청크(순위순)"
    )


class SecondFilterResult(BaseModel):

    search_set_id: int = Field(description="검색세트 ID")
    company_id: int = Field(description="회사 ID")
    results: list[NoticeSoftResult] = Field(
        default_factory=list, description="하드필터 통과 공고들의 매칭 결과(매칭도 내림차순)"
    )
