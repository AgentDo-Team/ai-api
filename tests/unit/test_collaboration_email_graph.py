"""협업 제안 이메일 서브그래프 HITL 흐름 단위 테스트 (DB/Gmail 없이).

graph 모듈의 DB 세션/서비스/발송 함수를 가짜로 갈아끼우고
compose → interrupt(HITL) → 승인/취소 재개 흐름을 검증한다.
"""

from types import SimpleNamespace

import pytest
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.types import Command

import app.agents.collaboration_email.graph as graph_module
from app.agents.collaboration_email.graph import (
    _resume_to_approved,
    build_collaboration_email_graph,
)
from app.schemas.collaboration_email import CollaborationEmailDraft


class _FakeSessionCM:
    """async with async_session_factory() as session 흉내."""

    async def __aenter__(self):
        return SimpleNamespace()

    async def __aexit__(self, *exc):
        return False


class _FakeService:
    """CollaborationEmailService 대체 — 고정 초안을 반환한다."""

    def __init__(self, **kwargs):
        pass

    async def compose(self, *, company_id, partner_id, bid_notice_id, gap_description):
        return CollaborationEmailDraft(
            to="partner@x.io", subject="[협업 제안] 제목", body="본문입니다."
        )


@pytest.fixture
def patched_graph(monkeypatch):
    """DB/서비스/발송을 가짜로 갈아끼운 컴파일된 그래프 + 발송 호출 기록."""
    sent_calls: list[dict] = []

    def fake_send_email(*, to, subject, body, **_):
        sent_calls.append({"to": to, "subject": subject, "body": body})
        return {"id": "msg-123"}

    monkeypatch.setattr(graph_module, "async_session_factory", lambda: _FakeSessionCM())
    monkeypatch.setattr(graph_module, "CollaborationEmailService", _FakeService)
    monkeypatch.setattr(graph_module, "send_email", fake_send_email)

    # llm 은 _FakeService 가 무시하므로 아무 객체나 주입해 OpenAIProvider 생성을 피한다.
    # 단독 실행 시 HITL interrupt/resume 에는 checkpointer 가 필요하다(임베드 시엔 부모가 제공).
    graph = build_collaboration_email_graph(llm=object(), checkpointer=InMemorySaver())
    return graph, sent_calls


_INPUTS = {
    "company_id": 1,
    "partner_id": 2,
    "bid_notice_id": 3,
    "gap_description": "클라우드 실적 부족",
}


def test_resume_to_approved_variants():
    assert _resume_to_approved({"approved": True}) is True
    assert _resume_to_approved({"approved": False}) is False
    assert _resume_to_approved({}) is False
    assert _resume_to_approved(True) is True
    assert _resume_to_approved(False) is False


async def test_compose_then_interrupt(patched_graph):
    graph, _ = patched_graph
    config = {"configurable": {"thread_id": "t-interrupt"}}

    result = await graph.ainvoke(_INPUTS, config=config)

    interrupts = result["__interrupt__"]
    payload = interrupts[0].value
    assert payload["action"] == "review_collaboration_email"
    assert payload["draft"]["to"] == "partner@x.io"
    assert payload["draft"]["subject"] == "[협업 제안] 제목"


async def test_approve_sends_email(patched_graph):
    graph, sent_calls = patched_graph
    config = {"configurable": {"thread_id": "t-approve"}}

    await graph.ainvoke(_INPUTS, config=config)
    final = await graph.ainvoke(Command(resume={"approved": True}), config=config)

    assert final["status"] == "sent"
    assert final["sent_result"]["id"] == "msg-123"
    assert len(sent_calls) == 1
    assert sent_calls[0]["to"] == "partner@x.io"


async def test_cancel_does_not_send(patched_graph):
    graph, sent_calls = patched_graph
    config = {"configurable": {"thread_id": "t-cancel"}}

    await graph.ainvoke(_INPUTS, config=config)
    final = await graph.ainvoke(Command(resume={"approved": False}), config=config)

    assert final["status"] == "cancelled"
    assert sent_calls == []
