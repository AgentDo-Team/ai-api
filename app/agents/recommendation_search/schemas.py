"""보완점 검색 서브 에이전트의 LLM 구조화 출력(response_model) 스키마."""

from __future__ import annotations

from pydantic import BaseModel, Field


class SearchQueries(BaseModel):
    """약점(weakness) 1건을 보완하기 위한 웹 검색어 생성 결과."""

    queries: list[str] = Field(
        description="약점을 보완할 정보를 찾기 위한 웹 검색어 2~3개(한국어)",
        min_length=1,
    )


class SufficiencyJudgment(BaseModel):
    """검색 결과가 약점 보완에 충분한지에 대한 판정."""

    sufficient: bool = Field(description="검색 결과가 약점을 보완하기 충분한지 여부")
    reason: str = Field(description="판정 근거(한국어 1~2문장)")


class CompanyReport(BaseModel):
    """검색 결과들을 종합한 추천 회사 리포트."""

    report: str = Field(description="약점별 검색 결과를 종합한 추천 회사 리포트 본문(한국어)")
