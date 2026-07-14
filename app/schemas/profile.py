from datetime import datetime

from pydantic import BaseModel


class ProfileRequest(BaseModel):
    """자사 프로필(입력폼 1단계) 저장 요청.

    태그형 입력(주력 기술/사업, 보유 솔루션)은 프론트에서 문자열로 합쳐 보낸다.
    모든 필드는 선택값 — 임시저장/부분 입력을 허용하기 위함.
    """

    company_scale: str | None = None  # 기업 규모 (대/중/소)
    target_techs: str | None = None  # 주력 기술/사업
    offered_solutions: str | None = None  # 보유 솔루션
    strengths_diff: str | None = None  # 강점과 차별점
    credit_rating: str | None = None  # 신용평가등급
    sp_grade: str | None = None  # SP등급


class ProfileResponse(BaseModel):
    """자사 프로필 조회 응답."""

    id: int
    company_id: int
    company_scale: str | None = None
    target_techs: str | None = None
    offered_solutions: str | None = None
    strengths_diff: str | None = None
    credit_rating: str | None = None
    sp_grade: str | None = None
    updated_at: datetime | None = None
