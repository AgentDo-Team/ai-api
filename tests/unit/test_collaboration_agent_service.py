"""CollaborationAgentService 의 SSE 이벤트 흐름 단위 테스트 (그래프/DB 가짜).

run_stream(검색 분기 / 이메일 interrupt) 와 resume_stream(발송) 이 올바른 이벤트 dict 를
내보내고 최종 결과를 assistant 메시지로 저장하는지 검증한다.
"""

from types import SimpleNamespace

import pytest
from langgraph.types import Command

import app.services.collaboration_agent_service as svc_module
from app.services.collaboration_agent_service import CollaborationAgentService


class _Interrupt:
    def __init__(self, value):
        self.value = value


class _FakeGraph:
    """astream 스크립트와 최종 상태를 흉내내는 가짜 컴파일 그래프."""

    def __init__(self, run_script, resume_script, final_values):
        self._run_script = run_script
        self._resume_script = resume_script
        self._final_values = final_values

    async def astream(self, payload, *, config, stream_mode, subgraphs):
        script = self._resume_script if isinstance(payload, Command) else self._run_script
        for item in script:
            yield item

    async def aget_state(self, config):
        return SimpleNamespace(values=self._final_values)


class _FakeSearchSetRepo:
    async def get(self, session_id):
        return SimpleNamespace(id=session_id, company_id=1)


class _FakeChatRepo:
    def __init__(self):
        self.added = []

    async def add(self, message):
        message.id = 777
        self.added.append(message)
        return message


class _FakeSession:
    async def commit(self):
        pass

    async def refresh(self, obj):
        pass


def _service(monkeypatch, graph):
    monkeypatch.setattr(svc_module, "_graph", graph)
    return CollaborationAgentService(
        session=_FakeSession(),
        search_set_repo=_FakeSearchSetRepo(),
        chat_message_repo=_FakeChatRepo(),
    )


async def _collect(aiter):
    return [ev async for ev in aiter]


async def test_run_stream_search_branch(monkeypatch):
    run_script = [
        (("",), "custom", {"type": "node", "graph": "main", "node": "judge_partner"}),
        (("",), "custom", {"type": "node", "graph": "main", "node": "route", "branch": "search"}),
        (("s:1",), "custom", {"type": "node", "graph": "search", "node": "generate_query", "weakness_index": 0}),
        (("",), "custom", {"type": "node", "graph": "search", "node": "report"}),
    ]
    graph = _FakeGraph(run_script, [], {"branch": "search", "report": "최종 리포트"})
    service = _service(monkeypatch, graph)

    events = await _collect(service.run_stream(1, 10, 3))

    assert [e.get("node") for e in events if e["type"] == "node"] == [
        "judge_partner",
        "route",
        "generate_query",
        "report",
    ]
    done = events[-1]
    assert done["type"] == "done"
    assert done["status"] == "report"
    assert done["report"] == "최종 리포트"
    assert done["message_id"] == 777


async def test_run_stream_email_interrupt_then_resume(monkeypatch):
    draft = {"to": "a@x.io", "subject": "제목", "body": "본문"}
    run_script = [
        (("",), "custom", {"type": "node", "graph": "main", "node": "route", "branch": "email"}),
        (("",), "custom", {"type": "node", "graph": "email", "node": "compose_draft"}),
        (("child",), "updates", {"__interrupt__": (_Interrupt({"draft": draft}),)}),
    ]
    resume_script = [
        (("",), "custom", {"type": "node", "graph": "email", "node": "send_email"}),
    ]
    graph = _FakeGraph(
        run_script, resume_script, {"branch": "email", "status": "sent", "to": "a@x.io"}
    )
    service = _service(monkeypatch, graph)

    run_events = await _collect(service.run_stream(1, 10, 3))
    # interrupt 이벤트에서 멈춰야 한다(done 없음).
    assert run_events[-1]["type"] == "interrupt"
    assert run_events[-1]["draft"] == draft
    assert not any(e["type"] == "done" for e in run_events)

    resume_events = await _collect(service.resume_stream(1, 10, 3, True))
    assert any(e.get("node") == "send_email" for e in resume_events)
    done = resume_events[-1]
    assert done["type"] == "done"
    assert done["status"] == "sent"
    assert done["message_id"] == 777


async def test_run_stream_rejects_foreign_session(monkeypatch):
    class _ForeignRepo:
        async def get(self, session_id):
            return SimpleNamespace(id=session_id, company_id=999)

    monkeypatch.setattr(svc_module, "_graph", _FakeGraph([], [], {}))
    service = CollaborationAgentService(
        session=_FakeSession(),
        search_set_repo=_ForeignRepo(),
        chat_message_repo=_FakeChatRepo(),
    )
    from app.common.exceptions import AppException

    with pytest.raises(AppException):
        await _collect(service.run_stream(1, 10, 3))
