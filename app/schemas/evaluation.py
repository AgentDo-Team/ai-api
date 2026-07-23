from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class EvalCriterion(BaseModel):
    name: str = Field(description="세부평가 항목명", examples=["기술능력 평가"])
    description: str | None = Field(default=None, description="평가 항목 설명/기준")
    max_score: float = Field(description="배점(만점)", examples=[30.0])


class CriteriaExtractionResult(BaseModel):

    criteria: list[EvalCriterion]


class CriterionJudgment(BaseModel):

    verdict: Literal["found", "no_evidence"]
    chunk_id: int | None = Field(default=None, description="근거로 인용한 bid_notice 청크 ID")
    project_id: int | None = Field(default=None, description="근거로 인용한 company_project ID")
    field: str | None = Field(
        default=None, description="근거가 된 company_project/profile 필드명(예: performance)"
    )
    score: float = Field(description="이 회차에서 매긴 점수")
    reason: str = Field(description="채점 근거 요약")


class CriterionScoreResult(BaseModel):

    criterion: EvalCriterion
    earned_score: float = Field(description="K회 점수 평균")
    verdict: Literal["found", "no_evidence"] = Field(description="K회 중 다수결 verdict")
    chunk_id: int | None = None
    project_id: int | None = None
    field: str | None = None
    reason: str
    k_runs: list[CriterionJudgment]
