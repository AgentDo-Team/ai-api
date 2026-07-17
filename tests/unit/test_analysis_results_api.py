"""분석 결과 조회 엔드포인트(GET /bid-notices/search-sets/{id}/analysis-results) 테스트.

get_current_account / get_search_set_repository / get_analysis_repository 를 갈아끼워
DB 없이 라우터·인가·매핑 로직만 검증한다.
"""

import pytest
from httpx import ASGITransport, AsyncClient

from app.api.auth import get_current_account
from app.api.deps import get_analysis_repository, get_search_set_repository
from app.db.models.analysis import AnalysisResult
from app.db.models.bid import BidNotice
from app.db.models.company import Company
from app.db.models.search import SearchSet
from main import app


class FakeSearchSetRepository:
    def __init__(self, sets: dict[int, SearchSet]) -> None:
        self.sets = sets

    async def get(self, search_set_id: int) -> SearchSet | None:
        return self.sets.get(search_set_id)


class FakeAnalysisRepository:
    def __init__(self, rows: dict[int, list[tuple[AnalysisResult, BidNotice]]]) -> None:
        self.rows = rows

    async def list_by_search_set(
        self, search_set_id: int, limit: int = 5
    ) -> list[tuple[AnalysisResult, BidNotice]]:
        return self.rows.get(search_set_id, [])[:limit]


@pytest.fixture
async def analysis_client():
    sets = {
        1: SearchSet(id=1, company_id=1, title="테스트 검색", status="completed"),
        2: SearchSet(id=2, company_id=2, title="남의 검색", status="completed"),
        3: SearchSet(id=3, company_id=1, title="다건 검색", status="completed"),
    }
    rows = {
        1: [
            (
                AnalysisResult(
                    search_set_id=1,
                    bid_notice_id=10,
                    soft_score=88,
                    recommend_reason=[
                        {
                            "chunk_id": 5,
                            "reason": "클라우드 구축 경험 일치",
                            "cited_source": "project",
                            "cited_id": 3,
                            "cited_field": "performance",
                        }
                    ],
                    weaknesses=[],
                    summary="공공 클라우드 전환 사업",
                ),
                BidNotice(id=10, notice_no="A-1", title="클라우드 전환", demand_org="행정안전부"),
            ),
        ],
        # 상위 5건만 반환되는지 검증용 (7건 저장)
        3: [
            (
                AnalysisResult(
                    search_set_id=3, bid_notice_id=100 + i, soft_score=90 - i,
                    recommend_reason=[], weaknesses=[], summary=f"요약 {i}",
                ),
                BidNotice(id=100 + i, notice_no=f"B-{i}", title=f"공고 {i}", demand_org="기관"),
            )
            for i in range(7)
        ],
    }
    app.dependency_overrides[get_current_account] = lambda: Company(
        id=1, name="에이전트두", email="a@agentdo.io"
    )
    app.dependency_overrides[get_search_set_repository] = lambda: FakeSearchSetRepository(sets)
    app.dependency_overrides[get_analysis_repository] = lambda: FakeAnalysisRepository(rows)
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as c:
        yield c
    app.dependency_overrides.clear()


async def test_returns_mapped_analysis_results(analysis_client):
    response = await analysis_client.get("/bid-notices/search-sets/1/analysis-results")

    assert response.status_code == 200
    body = response.json()
    assert body["success"] is True
    assert body["data"]["search_set_id"] == 1
    results = body["data"]["results"]
    assert len(results) == 1
    item = results[0]
    assert item["final_score"] == 88
    assert item["title"] == "클라우드 전환"
    assert item["demand_org"] == "행정안전부"
    assert item["summary"] == "공공 클라우드 전환 사업"
    assert item["recommend_reason"][0]["reason"] == "클라우드 구축 경험 일치"
    assert item["weaknesses"] == []


async def test_returns_at_most_five_results(analysis_client):
    response = await analysis_client.get("/bid-notices/search-sets/3/analysis-results")

    assert response.status_code == 200
    assert len(response.json()["data"]["results"]) == 5


async def test_rejects_other_companys_search_set(analysis_client):
    response = await analysis_client.get("/bid-notices/search-sets/2/analysis-results")

    assert response.status_code == 403


async def test_404_when_search_set_not_found(analysis_client):
    response = await analysis_client.get("/bid-notices/search-sets/999/analysis-results")

    assert response.status_code == 404
