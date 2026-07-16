"""검색세트 상태 폴링 엔드포인트(GET /bid-notices/search-sets/{id}/status) 테스트.

get_current_account / get_search_set_repository 를 갈아끼워 DB 없이 라우터·인가 로직만 검증한다.
"""

import pytest
from httpx import ASGITransport, AsyncClient

from app.api.auth import get_current_account
from app.api.deps import get_search_set_repository
from app.db.models.company import Company
from app.db.models.search import SearchSet
from main import app


class FakeSearchSetRepository:
    def __init__(self, sets: dict[int, SearchSet]) -> None:
        self.sets = sets

    async def get(self, search_set_id: int) -> SearchSet | None:
        return self.sets.get(search_set_id)


@pytest.fixture
async def status_client():
    sets = {
        1: SearchSet(id=1, company_id=1, title="테스트 검색", status="ongoing_third_filter"),
        2: SearchSet(id=2, company_id=2, title="남의 검색", status="completed"),
    }
    app.dependency_overrides[get_current_account] = lambda: Company(
        id=1, name="에이전트두", email="a@agentdo.io"
    )
    app.dependency_overrides[get_search_set_repository] = lambda: FakeSearchSetRepository(sets)
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as c:
        yield c
    app.dependency_overrides.clear()


async def test_get_status_returns_own_search_set_status(status_client):
    response = await status_client.get("/bid-notices/search-sets/1/status")

    assert response.status_code == 200
    body = response.json()
    assert body["success"] is True
    assert body["data"] == {"search_set_id": 1, "status": "ongoing_third_filter"}


async def test_get_status_rejects_other_companys_search_set(status_client):
    response = await status_client.get("/bid-notices/search-sets/2/status")

    assert response.status_code == 403


async def test_get_status_404_when_not_found(status_client):
    response = await status_client.get("/bid-notices/search-sets/999/status")

    assert response.status_code == 404
