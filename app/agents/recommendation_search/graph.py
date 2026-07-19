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
from app.agents.recommendation_search.state import RecommendationState
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

    # 검색 에이전트를 컴파일된 서브그래프 노드로 직접 임베드한다(래퍼 .ainvoke() 미사용).
    # 그래야 각 약점 브랜치의 get_stream_writer() 커스텀 이벤트가 최상위 스트림까지
    # 전파돼 프론트가 병렬 진행 상황을 볼 수 있다. 서브그래프 마지막 collect 노드가
    # search_results(operator.add) 로 결과를 fan-in 한다.
    search_agent = build_search_agent(llm, tavily)
    report_node = make_report_node(llm)

    def dispatch(state: RecommendationState) -> list[Send]:
        """약점별로 검색 에이전트를 병렬 fan-out 한다(약점 순번 동봉)."""
        return [
            Send("search_agent", {"weakness": w, "weakness_index": i})
            for i, w in enumerate(state["weaknesses"])
        ]

    builder = StateGraph(RecommendationState)
    builder.add_node("search_agent", search_agent)
    builder.add_node("report", report_node)

    builder.add_conditional_edges(START, dispatch, ["search_agent"])
    builder.add_edge("search_agent", "report")
    builder.add_edge("report", END)

    return builder.compile()
