"""협업 제안 이메일 서브그래프.

메인 추천 그래프가 뽑은 약점(weakness)을 협력사가 보완해줄 수 있을 때, 협업 제안 메일을
보내기 위해 분기하는 서브그래프다.

구조:
  START → compose_draft → human_review ──(승인)──▶ send_email → END
                                  └──────(취소)──▶ END

동작: 메일 초안 작성(compose_draft) → HITL 검수(human_review, 승인/취소) → 발송(send_email).

HITL 은 langgraph interrupt/Command 로 구현한다. 프론트 챗봇 UI 연동 계약:
  1. graph.ainvoke(inputs, config={"configurable": {"thread_id": <채팅 세션 id>}}) 로 실행.
  2. 반환값에 "__interrupt__" 가 있으면 초안(to/subject/body)을 프론트에 노출하고 승인/취소를 받는다.
  3. graph.ainvoke(Command(resume={"approved": bool}), config=<같은 thread_id>) 로 재개한다.

interrupt 로 중단·재개하려면 checkpointer 가 필수라 InMemorySaver 로 컴파일한다(단일 프로세스용).

메인 랭그래프는 build_collaboration_email_graph() 로 이 서브그래프를 얻어
run_search_agent 처럼 래퍼 노드로 편입할 수 있다.
"""

from __future__ import annotations

import asyncio
import logging

from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.config import get_stream_writer
from langgraph.graph import END, START, StateGraph
from langgraph.types import interrupt

from app.agents.collaboration_email.state import CollaborationEmailState
from app.clients.gmail_client import send_email
from app.db.repositories.bid_notice_repository import BidNoticeRepository
from app.db.repositories.company_repository import CompanyRepository, PartnerRepository
from app.db.session import async_session_factory
from app.llm.base import LLMProvider
from app.llm.openai_provider import OpenAIProvider
from app.services.collaboration_email_service import CollaborationEmailService

logger = logging.getLogger(__name__)


def _resume_to_approved(decision: object) -> bool:
    """HITL 재개 값(Command(resume=...))에서 승인 여부를 읽는다.

    프론트는 {"approved": bool} 를 보내는 게 기본이지만, bool 단독도 허용한다.
    """
    if isinstance(decision, dict):
        return bool(decision.get("approved", False))
    return bool(decision)


def build_collaboration_email_graph(
    llm: LLMProvider | None = None,
    checkpointer: BaseCheckpointSaver | None = None,
):
    """협업 제안 이메일 서브그래프를 컴파일해 반환한다.

    llm 을 주입하지 않으면 기본 구현(OpenAIProvider)을 사용한다.

    checkpointer:
      - 단독 실행 시 InMemorySaver 등을 주입해야 interrupt/resume 이 동작한다.
      - 메인 그래프의 노드로 임베드할 땐 None 으로 컴파일해 부모(메인) 그래프의
        checkpointer 를 상속받는다. 그래야 interrupt 가 최상위 thread 로 전파돼
        같은 thread_id 로 Command(resume=...) 재개가 가능하다.
    """

    llm = llm or OpenAIProvider()

    async def compose_draft(state: CollaborationEmailState) -> dict:
        """회사/협력사/공고를 조회하고 LLM 으로 메일 초안(to/subject/body)을 만든다."""
        get_stream_writer()(
            {
                "type": "node",
                "graph": "email",
                "node": "compose_draft",
                "label": "이메일 작성 중",
            }
        )
        async with async_session_factory() as session:
            service = CollaborationEmailService(
                company_repo=CompanyRepository(session),
                partner_repo=PartnerRepository(session),
                bid_notice_repo=BidNoticeRepository(session),
                llm=llm,
            )
            draft = await service.compose(
                company_id=state["company_id"],
                partner_id=state["partner_id"],
                bid_notice_id=state["bid_notice_id"],
                gap_description=state["gap_description"],
            )
        logger.info("[email] 초안 작성 완료 → 수신자=%s", draft.to)
        return {
            "to": draft.to,
            "subject": draft.subject,
            "body": draft.body,
            "status": "drafted",
        }

    async def human_review(state: CollaborationEmailState) -> dict:
        """초안을 사람에게 노출하고 승인/취소를 받는다 (HITL).

        interrupt payload 는 프론트가 '어떤 회사에 어떤 메일을 보낼지' 보여주는 데 쓰인다.
        """
        decision = interrupt(
            {
                "action": "review_collaboration_email",
                "message": (
                    f"{state['to']} 주소로 아래 협업 제안 메일을 보냅니다. "
                    "승인하시겠습니까? (승인/취소)"
                ),
                "draft": {
                    "to": state["to"],
                    "subject": state["subject"],
                    "body": state["body"],
                },
            }
        )
        approved = _resume_to_approved(decision)
        logger.info("[email] 사람 검수 결과 → 승인=%s", approved)
        # 취소면 여기서 상태를 확정한다(발송 노드로 가지 않으므로). 승인이면 send_email 이 "sent" 로 덮는다.
        if approved:
            return {"approved": True}
        return {"approved": False, "status": "cancelled"}

    def route_after_review(state: CollaborationEmailState) -> str:
        """승인이면 발송, 취소면 종료한다."""
        return "send_email" if state.get("approved") else END

    async def send_email_node(state: CollaborationEmailState) -> dict:
        """Gmail API 로 초안을 발송한다.

        gmail_client.send_email 은 blocking(googleapiclient) 이라 이벤트 루프를 막지 않도록
        스레드로 오프로드한다.
        """
        get_stream_writer()(
            {
                "type": "node",
                "graph": "email",
                "node": "send_email",
                "label": "이메일 전송 중",
            }
        )
        result = await asyncio.to_thread(
            send_email,
            to=state["to"],
            subject=state["subject"],
            body=state["body"],
        )
        logger.info("[email] 발송 완료 → message id=%s", result.get("id"))
        return {"sent_result": result, "status": "sent"}

    builder = StateGraph(CollaborationEmailState)
    builder.add_node("compose_draft", compose_draft)
    builder.add_node("human_review", human_review)
    builder.add_node("send_email", send_email_node)

    builder.add_edge(START, "compose_draft")
    builder.add_edge("compose_draft", "human_review")
    builder.add_conditional_edges(
        "human_review",
        route_after_review,
        {"send_email": "send_email", END: END},
    )
    builder.add_edge("send_email", END)

    # interrupt 기반 HITL 은 checkpointer 가 있어야 중단 지점에서 재개할 수 있다.
    # 임베드 시엔 None 으로 컴파일해 부모 그래프의 checkpointer 를 상속받는다.
    return builder.compile(checkpointer=checkpointer)
