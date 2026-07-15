"""3차 필터 엔드포인트(라우터 계층) 테스트.

ThirdFilterService 를 가짜로 갈아끼우고 라우터·DTO 검증만 실제 코드를 태운다.
"""

import pytest
from httpx import ASGITransport, AsyncClient

from app.api.deps import get_third_filter_service
from app.schemas.third_filter import (
    FitReason,
    SkippedNotice,
    ThirdFilterNoticeRead,
    ThirdFilterResponse,
)
from main import app

CANNED_RESPONSE = ThirdFilterResponse(
    results=[
        ThirdFilterNoticeRead(
            bid_notice_id=12,
            final_score=82,
            aggregate_score=0.82,
            recommend_reason=[
                FitReason(
                    chunk_id=4821,
                    reason="유사 실적 확인",
                    cited_source="project",
                    cited_id=5,
                    cited_field="performance",
                )
            ],
            weaknesses=[],
            summary="○○공단 클라우드 전환 사업",
            title="○○공단 클라우드 전환 사업 제안요청",
            demand_org="○○공단",
        )
    ],
    skipped=[SkippedNotice(bid_notice_id=99, reason="채점 중 오류가 발생했습니다.")],
)


class FakeThirdFilterService:
    def __init__(self) -> None:
        self.received = None

    async def run(self, req) -> ThirdFilterResponse:
        self.received = req
        return CANNED_RESPONSE


VALID_BODY = {
    "search_set_id": 1,
    "company_id": 1,
    "results": [
        {
            "bid_notice_id": 12,
            "aggregate_score": 0.82,
            "ranked_chunks": [
                {
                    "chunk_id": 4821,
                    "rank": 1,
                    "score": 0.91,
                    "matched_source": "project",
                    "matched_id": 5,
                }
            ],
        }
    ],
}


@pytest.fixture
def fake_service() -> FakeThirdFilterService:
    return FakeThirdFilterService()


@pytest.fixture
async def tf_client(fake_service):
    app.dependency_overrides[get_third_filter_service] = lambda: fake_service
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as c:
        yield c
    app.dependency_overrides.clear()


async def test_run_third_filter_returns_wrapped_results(tf_client, fake_service):
    response = await tf_client.post("/api/third-filter", json=VALID_BODY)

    assert response.status_code == 200
    body = response.json()
    assert body["success"] is True
    assert body["message"] == "3차 필터 분석이 완료되었습니다."

    data = body["data"]
    assert len(data["results"]) == 1
    top = data["results"][0]
    assert top["bid_notice_id"] == 12
    assert top["final_score"] == 82
    assert "soft_score" not in top
    assert top["title"] == "○○공단 클라우드 전환 사업 제안요청"
    assert top["demand_org"] == "○○공단"
    assert len(top["recommend_reason"]) == 1
    assert top["recommend_reason"][0]["chunk_id"] == 4821
    assert top["recommend_reason"][0]["cited_source"] == "project"
    assert top["weaknesses"] == []
    assert data["skipped"][0]["bid_notice_id"] == 99

    # 요청 DTO 가 서비스까지 그대로 전달됐는지
    assert fake_service.received.search_set_id == 1
    assert fake_service.received.results[0].ranked_chunks[0].chunk_id == 4821


async def test_empty_results_rejected(tf_client):
    body = {**VALID_BODY, "results": []}
    response = await tf_client.post("/api/third-filter", json=body)
    assert response.status_code == 422


async def test_missing_required_field_rejected(tf_client):
    body = {"company_id": 1, "results": VALID_BODY["results"]}  # search_set_id 누락
    response = await tf_client.post("/api/third-filter", json=body)
    assert response.status_code == 422


async def test_invalid_matched_source_rejected(tf_client):
    body = {
        **VALID_BODY,
        "results": [
            {
                "bid_notice_id": 12,
                "aggregate_score": 0.82,
                "ranked_chunks": [
                    {
                        "chunk_id": 4821,
                        "rank": 1,
                        "score": 0.91,
                        "matched_source": "invalid",
                        "matched_id": 5,
                    }
                ],
            }
        ],
    }
    response = await tf_client.post("/api/third-filter", json=body)
    assert response.status_code == 422
