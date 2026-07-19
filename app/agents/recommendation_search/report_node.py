"""추천 회사 리포트 작성 노드.

검색 에이전트들이 약점별로 수집한 검색 결과(state["search_results"])를 종합해
하나의 추천 회사 리포트 텍스트를 생성한다.
"""

from __future__ import annotations

import logging

from langgraph.config import get_stream_writer

from app.agents.recommendation_search.schemas import CompanyReport
from app.agents.recommendation_search.state import RecommendationState, WeaknessSearchResult
from app.llm.base import LLMProvider

logger = logging.getLogger(__name__)

_REPORT_SYSTEM = (
    "너는 입찰공고 분석 리포트 작성자다. 회사가 이 공고에 참여할 때의 약점(weakness)들과, "
    "각 약점을 보완하기 위해 수집한 웹 검색 결과가 주어진다. 검색 결과에 근거해 각 약점을 "
    "어떤 회사·기술·솔루션으로 보완할 수 있는지 정리한 '추천 회사 리포트'를 한국어로 작성하라. "
    "검색 결과에 없는 사실을 지어내지 말고, 약점별로 근거와 추천을 명확히 구분해 서술하라."
)

# 약점 1건의 검색 결과(WeaknessSearchResult)를 LLM 프롬프트에 넣을 텍스트 한 덩어리로 변환하는 헬퍼
def _format_one(item: WeaknessSearchResult) -> str:
    lines = [f"## 약점: {item['weakness']}"]
    lines.append(f"(검색 충분성 판정: {'충분' if item.get('sufficient') else '부족'})")
    for r in item.get("tavily_results", []):
        title = r.get("title", "")
        url = r.get("url", "")
        content = (r.get("content", "") or "")[:500]
        lines.append(f"- {title} ({url})\n  {content}")
    return "\n".join(lines)


def make_report_node(llm: LLMProvider):
    """리포트 작성 노드 함수를 생성해 반환한다."""

    async def report(state: RecommendationState) -> dict:
        get_stream_writer()(
            {
                "type": "node",
                "graph": "search",
                "node": "report",
                "label": "최종 리포트 생성 중",
            }
        )
        search_results = state.get("search_results", [])
        user = "\n\n".join(_format_one(item) for item in search_results)
        result = await llm.complete_structured(
            system=_REPORT_SYSTEM,
            user=user or "(수집된 검색 결과 없음)",
            response_model=CompanyReport,
        )
        logger.info("[report] 약점 %d건 종합 리포트 생성 완료", len(search_results))
        return {"report": result.report}

    return report
