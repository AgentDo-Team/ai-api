"""협업 제안 이메일 서브그래프의 LangGraph 상태 정의."""

from __future__ import annotations

from typing import TypedDict


class CollaborationEmailState(TypedDict, total=False):
    """협업 제안 이메일 서브그래프 상태.

    입력(메인 그래프/호출자가 채워줌):
        company_id: 우리 회사 id.
        partner_id: 협업 제안을 보낼 협력사(Partner) id.
        bid_notice_id: 협업이 필요한 입찰공고 id.
        gap_description: 협력사가 보완해줄 수 있는 부족한 부분(약점) 설명.

    compose_draft 산출:
        to / subject / body: 검수·발송에 그대로 쓰는 메일 초안.

    HITL / 결과:
        approved: 사람 검수 결과(승인 True / 취소 False).
        status: "drafted" → "sent" | "cancelled".
        sent_result: Gmail 발송 응답(message id 등).
    """

    # 입력
    company_id: int
    partner_id: int
    bid_notice_id: int
    gap_description: str

    # compose 산출 (메일 초안)
    to: str
    subject: str
    body: str

    # HITL / 결과
    approved: bool
    status: str
    sent_result: dict
