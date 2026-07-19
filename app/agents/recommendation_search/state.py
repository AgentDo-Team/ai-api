"""보완점 검색 서브 에이전트의 LangGraph 상태 정의."""

from __future__ import annotations

import operator
from typing import Annotated, TypedDict


class WeaknessSearchResult(TypedDict):
    """검색 에이전트가 약점 1건을 처리한 최종 결과 패키지."""

    weakness: str
    queries: list[str]
    tavily_results: list[dict]
    sufficient: bool
    judge_reason: str


class SearchAgentState(TypedDict, total=False):
    """검색 에이전트 서브그래프 내부 상태(약점 1건 단위)."""

    weakness: str
    queries: list[str]
    tavily_results: list[dict]
    sufficient: bool
    judge_reason: str
    # generate_query 를 몇 번 수행했는지. 1회차는 한국어, 2회차는 영어 검색어를 생성한다.
    attempt: int


class RecommendationState(TypedDict, total=False):
    """최상위 그래프 상태.

    weaknesses: 입력(약점 텍스트 리스트).
    search_results: 약점별 검색 결과. Send fan-out 으로 병렬 생성되므로
        operator.add 리듀서로 fan-in(병합)한다.
    report: 최종 추천 회사 리포트 출력.
    """

    weaknesses: list[str]
    search_results: Annotated[list[WeaknessSearchResult], operator.add]
    report: str
