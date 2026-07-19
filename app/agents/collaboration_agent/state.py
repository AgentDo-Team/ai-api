"""회사 약점 해결 에이전트(메인 그래프)의 LangGraph 상태 정의.

메인 그래프는 이메일 서브그래프(CollaborationEmailState)와 검색 서브그래프
(RecommendationState)를 노드로 임베드한다. 서브그래프가 읽고/쓰는 키를 모두 포함하는
superset TypedDict 로 정의해야 임베드 시 상태가 정상 전달·병합된다.
"""

from __future__ import annotations

import operator
from typing import Annotated, TypedDict

from app.agents.recommendation_search.state import WeaknessSearchResult


class CollaborationAgentState(TypedDict, total=False):
    """회사 약점 해결 에이전트 최상위 상태.

    입력(호출자가 채움):
        company_id: 우리 회사 id.
        search_set_id: 채팅 세션(=검색 세트) id. 협력사 조회 tool 의 키이기도 하다.
        bid_notice_id: 약점 분석이 끝난 대상 공고 id.

    judge_partner 산출:
        weaknesses: 상위 3개 약점 텍스트. 검색 서브그래프의 입력으로도 쓰인다.
        can_resolve: 협력사가 약점을 해소할 수 있는지 여부.
        gap_description: 협력사가 보완해줄 부족한 부분 설명(이메일 서브그래프 입력).
        judge_reason: 판단 근거.
        branch: 분기 결정("email" | "search").

    이메일 서브그래프 키(CollaborationEmailState 와 공유):
        partner_id: 협업 제안을 보낼 협력사 id.
        to / subject / body: 메일 초안.
        approved / status / sent_result: HITL 결과·발송 결과.

    검색 서브그래프 키(RecommendationState 와 공유):
        search_results: 약점별 검색 결과(operator.add 로 fan-in).
        report: 최종 추천 회사 리포트.
    """

    # 입력
    company_id: int
    search_set_id: int
    bid_notice_id: int

    # judge_partner 산출
    weaknesses: list[str]
    can_resolve: bool
    gap_description: str
    judge_reason: str
    branch: str

    # 이메일 서브그래프 공유 키
    partner_id: int
    to: str
    subject: str
    body: str
    approved: bool
    status: str
    sent_result: dict

    # 검색 서브그래프 공유 키
    search_results: Annotated[list[WeaknessSearchResult], operator.add]
    report: str
