from __future__ import annotations

import logging

from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.config import get_stream_writer
from langgraph.graph import END, START, StateGraph
from tavily import AsyncTavilyClient

from app.agents.collaboration_agent.schemas import PartnerJudgment
from app.agents.collaboration_agent.state import CollaborationAgentState
from app.agents.collaboration_email.graph import build_collaboration_email_graph
from app.agents.recommendation_search.graph import build_recommendation_graph
from app.core.config import settings
from app.db.repositories.analysis_repository import AnalysisResultRepository
from app.db.session import async_session_factory
from app.llm.base import LLMProvider
from app.llm.openai_provider import OpenAIProvider
from app.tools.partner_tools import list_partners

logger = logging.getLogger(__name__)

# 상위 몇 개의 약점을 검색 서브그래프로 넘길지. (약점은 총 5개지만 상위 3개만 처리)
_TOP_WEAKNESSES = 3

_JUDGE_SYSTEM = (
    "너는 입찰공고 공동수급 전략가다. 우리 회사가 특정 공고를 수행할 때의 '약점(weakness)' 목록과 "
    "우리가 보유한 '협력사' 목록이 주어진다. 협력사들의 사업분야·기술스택·설명을 근거로, 이 약점들을 "
    "실질적으로 보완해 줄 수 있는 협력사가 있는지 판단하라. 있으면 can_resolve=true 로 하고 가장 적합한 "
    "협력사 하나를 partner_index(0-base 순번)로 지목하며, 그 협력사가 어떤 부족한 부분을 보완해 주는지 "
    "gap_description 에 1~2문장으로 적어라. 적합한 협력사가 없으면 can_resolve=false, partner_index=null "
    "로 답하라. 근거 없이 지어내지 마라."
)


def _format_weaknesses(weaknesses: list[str]) -> str:
    return "\n".join(f"{i + 1}. {w}" for i, w in enumerate(weaknesses)) or "(약점 없음)"


def _format_partners(partners: list[dict]) -> str:
    if not partners:
        return "(보유 협력사 없음)"
    lines = []
    for i, p in enumerate(partners):
        lines.append(
            f"[{i}] {p.get('name')} | 분야: {p.get('domain')} | 기술: {p.get('tech_stack')}\n"
            f"    설명: {p.get('description')}"
        )
    return "\n".join(lines)


def build_collaboration_agent_graph(
    llm: LLMProvider | None = None,
    tavily: AsyncTavilyClient | None = None,
    checkpointer: BaseCheckpointSaver | None = None,
):

    llm = llm or OpenAIProvider()
    tavily = tavily or AsyncTavilyClient(api_key=settings.tavily_api_key)

    async def judge_partner(state: CollaborationAgentState) -> dict:
        writer = get_stream_writer()
        writer(
            {
                "type": "node",
                "graph": "main",
                "node": "judge_partner",
                "label": "협력사로 약점 해결 가능 여부 판단 중",
            }
        )

        search_set_id = state["search_set_id"]
        bid_notice_id = state["bid_notice_id"]

        # 1) 약점 로드 (상위 3개). AnalysisResult.weaknesses = [{reason, ...}, ...]
        async with async_session_factory() as session:
            analysis = await AnalysisResultRepository(
                session
            ).get_by_search_set_and_notice(search_set_id, bid_notice_id)
        raw_weaknesses = (analysis.weaknesses if analysis else None) or []
        weaknesses = [
            str(w.get("reason", "")).strip()
            for w in raw_weaknesses[:_TOP_WEAKNESSES]
            if str(w.get("reason", "")).strip()
        ]

        # 2) 협력사 조회 tool 사용 (id/email 포함)
        partners = await list_partners.ainvoke({"search_set_id": search_set_id})

        # 약점이 없으면 판단할 대상이 없으니 검색 분기로 보낸다(안전 처리).
        if not weaknesses:
            logger.info("[main] 약점 없음 → 검색 분기")
            writer(
                {
                    "type": "node",
                    "graph": "main",
                    "node": "route",
                    "label": "분기 결정",
                    "branch": "search",
                }
            )
            return {"weaknesses": [], "can_resolve": False, "branch": "search"}

        # 3) LLM 판단
        judgment = await llm.complete_structured(
            system=_JUDGE_SYSTEM,
            user=(
                f"[약점 목록]\n{_format_weaknesses(weaknesses)}\n\n"
                f"[보유 협력사]\n{_format_partners(partners)}"
            ),
            response_model=PartnerJudgment,
        )

        # 4) partner_index → 실제 협력사 매핑 + 이메일 유무 검증
        partner = None
        if (
            judgment.can_resolve
            and judgment.partner_index is not None
            and 0 <= judgment.partner_index < len(partners)
        ):
            partner = partners[judgment.partner_index]

        # 협력사가 약점을 해소 가능하고 수신 이메일까지 있으면 이메일 분기, 아니면 검색 분기.
        if partner and partner.get("email"):
            logger.info(
                "[main] 협력사 해소 가능 → 이메일 분기 (partner=%s)", partner.get("name")
            )
            branch = "email"
            updates = {
                "weaknesses": weaknesses,
                "can_resolve": True,
                "partner_id": partner["id"],
                "gap_description": judgment.gap_description,
                "judge_reason": judgment.reason,
                "branch": branch,
            }
        else:
            reason = (
                "협력사에 등록된 이메일이 없음"
                if partner
                else "약점을 해소할 협력사 없음"
            )
            logger.info("[main] %s → 검색 분기", reason)
            branch = "search"
            updates = {
                "weaknesses": weaknesses,
                "can_resolve": False,
                "judge_reason": judgment.reason,
                "branch": branch,
            }

        writer(
            {
                "type": "node",
                "graph": "main",
                "node": "route",
                "label": "분기 결정",
                "branch": branch,
            }
        )
        return updates

    def route_after_judge(state: CollaborationAgentState) -> str:
        return "email" if state.get("branch") == "email" else "search"

    # 서브그래프는 checkpointer 미주입(None)으로 임베드해 부모의 checkpointer 를 상속한다.
    email_graph = build_collaboration_email_graph(llm)
    search_graph = build_recommendation_graph(llm, tavily)

    builder = StateGraph(CollaborationAgentState)
    builder.add_node("judge_partner", judge_partner)
    builder.add_node("email", email_graph)
    builder.add_node("search", search_graph)

    builder.add_edge(START, "judge_partner")
    builder.add_conditional_edges(
        "judge_partner",
        route_after_judge,
        {"email": "email", "search": "search"},
    )
    builder.add_edge("email", END)
    builder.add_edge("search", END)

    return builder.compile(checkpointer=checkpointer or InMemorySaver())
