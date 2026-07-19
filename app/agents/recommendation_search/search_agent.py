"""검색 에이전트 서브그래프.

약점(weakness) 1건을 입력받아:
  generate_query → tavily_search → judge
순서로 처리한다. judge 는 충분성 판정을 기록만 하고 항상 종료로 진행한다(재검색 루프 없음).
"""

from __future__ import annotations

import asyncio
import logging

from langgraph.graph import END, START, StateGraph
from tavily import AsyncTavilyClient

from app.agents.recommendation_search.schemas import SearchQueries, SufficiencyJudgment
from app.agents.recommendation_search.state import SearchAgentState
from app.core.config import settings
from app.llm.base import LLMProvider

logger = logging.getLogger(__name__)

_QUERY_SYSTEM = (
    "너는 입찰공고 분석의 '약점(weakness)'을 보완할 협력사·기술·솔루션을 웹에서 찾기 위한 "
    "검색 전문가다. 주어진 약점을 해소해 줄 회사나 정보를 찾을 수 있는 한국어 웹 검색어 "
    "2~3개를 생성하라. 검색어는 구체적이고 서로 다른 관점을 담아야 한다."
)

_QUERY_SYSTEM_ENG = (
    "너는 입찰공고 분석의 '약점(weakness)'을 보완할 협력사·기술·솔루션을 웹에서 찾기 위한 "
    "검색 전문가다. 주어진 약점을 해소해 줄 회사나 정보를 찾을 수 있는 영어 웹 검색어 "
    "2~3개를 생성하라. 검색어는 구체적이고 서로 다른 관점을 담아야 한다."
)

_JUDGE_SYSTEM = (
    "너는 검색 결과 평가자다. 주어진 약점(weakness)과 그 약점을 보완하려고 수집한 웹 검색 결과를 "
    "보고, 이 결과가 약점을 보완(해결)하기에 충분한 정보를 담고 있는지 판단하라. "
    "충분하면 sufficient=true, 부족하면 false 로 답하고 근거를 한 줄로 남겨라."
)

# tavily_api 검색결과를 텍스트 형태로
def _format_results(tavily_results: list[dict]) -> str:
    lines = []
    for r in tavily_results:
        title = r.get("title", "")
        url = r.get("url", "")
        content = (r.get("content", "") or "")[:500]
        lines.append(f"- {title} ({url})\n  {content}")
    return "\n".join(lines) if lines else "(검색 결과 없음)"


def build_search_agent(llm: LLMProvider, tavily: AsyncTavilyClient):
    """검색 에이전트 서브그래프를 컴파일해 반환한다."""

    async def generate_query(state: SearchAgentState) -> dict:
        weakness = state["weakness"]
        result = await llm.complete_structured(
            system=_QUERY_SYSTEM,
            user=f"약점: {weakness}",
            response_model=SearchQueries,
        )
        logger.info("[search] 약점=%r → 검색어=%s", weakness, result.queries)
        return {"queries": result.queries}

    async def tavily_search(state: SearchAgentState) -> dict:
        queries = state["queries"]
        searches = await asyncio.gather(
            *(
                tavily.search(query=q, max_results=settings.tavily_max_results)
                for q in queries
            ),
            return_exceptions=True,
        )
        results: list[dict] = []
        for q, res in zip(queries, searches):
            if isinstance(res, Exception):
                logger.warning("[search] Tavily 검색 실패 query=%r: %s", q, res)
                continue
            results.extend(res.get("results", []))
        logger.info("[search] 약점=%r → 검색결과 %d건", state["weakness"], len(results))
        return {"tavily_results": results}

    async def judge(state: SearchAgentState) -> dict:
        judgment = await llm.complete_structured(
            system=_JUDGE_SYSTEM,
            user=(
                f"약점: {state['weakness']}\n\n"
                f"검색 결과:\n{_format_results(state['tavily_results'])}"
            ),
            response_model=SufficiencyJudgment,
        )
        logger.info(
            "[search] 약점=%r → 충분성=%s (%s)",
            state["weakness"],
            judgment.sufficient,
            judgment.reason,
        )
        # 재검색 루프 없이 판정만 기록하고 종료로 진행한다.
        return {"sufficient": judgment.sufficient, "judge_reason": judgment.reason}

    builder = StateGraph(SearchAgentState)
    builder.add_node("generate_query", generate_query)
    builder.add_node("tavily_search", tavily_search)
    builder.add_node("judge", judge)

    builder.add_edge(START, "generate_query")
    builder.add_edge("generate_query", "tavily_search")
    builder.add_edge("tavily_search", "judge")
    builder.add_edge("judge", END)

    return builder.compile()
