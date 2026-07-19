"""회사 약점 해결 에이전트 메인 그래프의 분기 로직 단위 테스트 (DB/LLM/네트워크 없이).

judge_partner 가 약점/협력사/LLM 판단을 근거로 email/search 로 올바르게 분기하는지,
그리고 각 노드가 커스텀 상태 이벤트를 발행하는지 검증한다. 서브그래프는 진입 여부만
기록하는 가짜로 갈아끼운다.
"""

from types import SimpleNamespace

import pytest
from langgraph.graph import END, START, StateGraph

import app.agents.collaboration_agent.graph as graph_module
from app.agents.collaboration_agent.schemas import PartnerJudgment
from app.agents.collaboration_agent.state import CollaborationAgentState


class _FakeSessionCM:
    async def __aenter__(self):
        return SimpleNamespace()

    async def __aexit__(self, *exc):
        return False


def _fake_analysis_repo(weaknesses):
    class _Repo:
        def __init__(self, session):
            pass

        async def get_by_search_set_and_notice(self, search_set_id, bid_notice_id):
            return SimpleNamespace(weaknesses=weaknesses)

    return _Repo


def _fake_list_partners(partners):
    async def _ainvoke(args):
        return partners

    return SimpleNamespace(ainvoke=_ainvoke)


class _FakeLLM:
    def __init__(self, judgment):
        self._judgment = judgment

    async def complete_structured(self, *, system, user, response_model, model=None):
        assert response_model is PartnerJudgment
        return self._judgment


def _marker_subgraph(name: str, marker: list):
    """진입 시 이름을 기록하고 끝나는 트리비얼 서브그래프."""

    async def enter(state: CollaborationAgentState) -> dict:
        marker.append(name)
        return {"status": "sent"} if name == "email" else {"report": "리포트"}

    b = StateGraph(CollaborationAgentState)
    b.add_node(name, enter)
    b.add_edge(START, name)
    b.add_edge(name, END)
    return b.compile()


def _build(monkeypatch, *, weaknesses, partners, judgment):
    marker: list[str] = []
    monkeypatch.setattr(graph_module, "async_session_factory", lambda: _FakeSessionCM())
    monkeypatch.setattr(
        graph_module, "AnalysisResultRepository", _fake_analysis_repo(weaknesses)
    )
    monkeypatch.setattr(graph_module, "list_partners", _fake_list_partners(partners))
    monkeypatch.setattr(
        graph_module,
        "build_collaboration_email_graph",
        lambda llm: _marker_subgraph("email", marker),
    )
    monkeypatch.setattr(
        graph_module,
        "build_recommendation_graph",
        lambda llm, tavily: _marker_subgraph("search", marker),
    )
    graph = graph_module.build_collaboration_agent_graph(
        llm=_FakeLLM(judgment), tavily=object()
    )
    return graph, marker


_INPUTS = {"company_id": 1, "search_set_id": 2, "bid_notice_id": 3}


async def _run(graph):
    config = {"configurable": {"thread_id": "t"}}
    events = []
    async for _ns, mode, chunk in graph.astream(
        _INPUTS, config=config, stream_mode=["custom", "updates"], subgraphs=True
    ):
        if mode == "custom":
            events.append(chunk)
    return events


async def test_routes_to_email_when_partner_resolves(monkeypatch):
    graph, marker = _build(
        monkeypatch,
        weaknesses=[{"reason": "클라우드 실적 부족"}],
        partners=[{"id": 9, "name": "협력사A", "email": "a@x.io"}],
        judgment=PartnerJudgment(
            can_resolve=True, partner_index=0, gap_description="클라우드 보완", reason="적합"
        ),
    )
    events = await _run(graph)
    assert marker == ["email"]
    route = next(e for e in events if e["node"] == "route")
    assert route["branch"] == "email"


async def test_routes_to_search_when_partner_has_no_email(monkeypatch):
    graph, marker = _build(
        monkeypatch,
        weaknesses=[{"reason": "AI 경험 부족"}],
        partners=[{"id": 9, "name": "협력사A", "email": None}],
        judgment=PartnerJudgment(
            can_resolve=True, partner_index=0, gap_description="보완", reason="적합"
        ),
    )
    events = await _run(graph)
    assert marker == ["search"]
    route = next(e for e in events if e["node"] == "route")
    assert route["branch"] == "search"


async def test_routes_to_search_when_cannot_resolve(monkeypatch):
    graph, marker = _build(
        monkeypatch,
        weaknesses=[{"reason": "특수 실적 부족"}],
        partners=[{"id": 9, "name": "협력사A", "email": "a@x.io"}],
        judgment=PartnerJudgment(
            can_resolve=False, partner_index=None, gap_description="", reason="협력사 없음"
        ),
    )
    events = await _run(graph)
    assert marker == ["search"]


async def test_no_weakness_routes_to_search_without_llm(monkeypatch):
    # 약점이 없으면 LLM 을 부르지 않고 바로 검색 분기. LLM 을 호출하면 예외로 실패하게 둔다.
    class _BoomLLM:
        async def complete_structured(self, **kwargs):
            raise AssertionError("약점이 없으면 LLM 을 부르면 안 된다")

    graph, marker = _build(
        monkeypatch,
        weaknesses=[],
        partners=[{"id": 9, "name": "협력사A", "email": "a@x.io"}],
        judgment=None,
    )
    # _build 가 넣은 _FakeLLM 을 _BoomLLM 으로 교체
    graph, marker = (
        graph_module.build_collaboration_agent_graph(llm=_BoomLLM(), tavily=object()),
        marker,
    )
    events = await _run(graph)
    route = next(e for e in events if e["node"] == "route")
    assert route["branch"] == "search"
