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
    if isinstance(decision, dict):
        return bool(decision.get("approved", False))
    return bool(decision)


def build_collaboration_email_graph(
    llm: LLMProvider | None = None,
    checkpointer: BaseCheckpointSaver | None = None,
):
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
    return builder.compile(checkpointer=checkpointer)
