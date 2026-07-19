"""보완점 검색 서브 에이전트 단독 실행 러너 (테스트용).

입력(약점)을 아래 SAMPLE_WEAKNESSES 에 텍스트로 직접 넣어 이 서브 에이전트만 단독 실행한다.

실행:
    uv run --env-file .env python -m app.agents.recommendation_search
    (config.py 에 tavily_api_key 필드가 있으므로 아래처럼 --env-file 없이도 동작한다)
    uv run python -m app.agents.recommendation_search
"""

from __future__ import annotations

import asyncio
import logging

from app.agents.recommendation_search.graph import build_recommendation_graph

SAMPLE_WEAKNESSES = [
    "공고가 요구하는 미국의 펜더(fender) 회사와의 협업 실적이 회사에 없음",
    "공고가 요구하는 미국의 깁슨(gibson) 회사와의 협업 실적이 회사에 없음",
]

SAMPLE_WEAKNESSES2 = [
    "공고가 요구하는 대규모 공공 클라우드 전환 구축 실적이 회사에 없음",
    "AI 챗봇/LLM 기반 서비스 구축 경험이 부족함",
]


async def main() -> None:
    graph = build_recommendation_graph()
    final = await graph.ainvoke({"weaknesses": SAMPLE_WEAKNESSES})

    print("\n" + "=" * 60)
    print("추천 회사 리포트")
    print("=" * 60)
    print(final["report"])


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(levelname)s %(name)s: %(message)s",
    )
    asyncio.run(main())
