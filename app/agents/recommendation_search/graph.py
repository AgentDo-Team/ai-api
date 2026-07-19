"""보완점 검색 서브 에이전트 최상위 그래프.

구조 (map-reduce):
  START ──dispatch(Send)──▶ search_agent (약점별 병렬 fan-out)
                              │
                              ▼ (operator.add 리듀서로 fan-in)
                           report ──▶ END

메인 랭그래프는 build_recommendation_graph() 로 이 서브 에이전트를 얻어 노드로 편입할 수 있다.
"""

from __future__ import annotations

import logging

from langgraph.graph import END, START, StateGraph
from langgraph.types import Send
from tavily import AsyncTavilyClient

from app.agents.recommendation_search.report_node import make_report_node
from app.agents.recommendation_search.search_agent import build_search_agent
from app.agents.recommendation_search.state import RecommendationState, SearchAgentState
from app.core.config import settings
from app.llm.base import LLMProvider
from app.llm.openai_provider import OpenAIProvider

logger = logging.getLogger(__name__)


def build_recommendation_graph(
    llm: LLMProvider | None = None,
    tavily: AsyncTavilyClient | None = None,
):
    """보완점 검색 서브 에이전트 그래프를 컴파일해 반환한다.

    llm / tavily 를 주입하지 않으면 기본 구현(OpenAIProvider, AsyncTavilyClient)을 사용한다.
    """

    llm = llm or OpenAIProvider()
    tavily = tavily or AsyncTavilyClient(api_key=settings.tavily_api_key)

    search_agent = build_search_agent(llm, tavily)
    report_node = make_report_node(llm)

    async def run_search_agent(state: SearchAgentState) -> dict:
        """검색 서브그래프를 실행하고 결과를 최상위 리듀서에 맞게 패키징한다."""
        result = await search_agent.ainvoke({"weakness": state["weakness"]})
        return {
            "search_results": [
                {
                    "weakness": result["weakness"],
                    "queries": result.get("queries", []),
                    "tavily_results": result.get("tavily_results", []),
                    "sufficient": result.get("sufficient", False),
                    "judge_reason": result.get("judge_reason", ""),
                }
            ]
        }

    def dispatch(state: RecommendationState) -> list[Send]:
        """약점별로 검색 에이전트를 병렬 fan-out 한다."""
        return [Send("search_agent", {"weakness": w}) for w in state["weaknesses"]]

    builder = StateGraph(RecommendationState)
    builder.add_node("search_agent", run_search_agent)
    builder.add_node("report", report_node)

    builder.add_conditional_edges(START, dispatch, ["search_agent"])
    builder.add_edge("search_agent", "report")
    builder.add_edge("report", END)

    return builder.compile()
