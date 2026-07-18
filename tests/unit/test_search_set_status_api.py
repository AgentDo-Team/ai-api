"""검색세트 상태 SSE 스트림 엔드포인트
(GET /bid-notices/search-sets/{id}/status/stream) 테스트.

소유권 검증(403/404)은 스트림이 열리기 전에 수행되므로 주입된 fake 리포지토리로 검증한다.
스트림 본문은 `_read_status` 를 갈아끼워 가짜 상태 시퀀스를 흘려보내며 검증한다(DB 불필요).
"""

import json

import pytest
from httpx import ASGITransport, AsyncClient

from app.api import search as search_api
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
        1: SearchSet(
            id=1,
            company_id=1,
            title="테스트 검색",
            status="ongoing_third_filter",
            progress_current=3,
            progress_total=10,
        ),
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


def _parse_sse(body: str) -> list[dict]:
    """SSE 본문(`data: {json}\n\n` 블록들)을 이벤트 dict 리스트로 파싱한다."""
    events = []
    for block in body.split("\n\n"):
        line = next((l for l in block.split("\n") if l.startswith("data:")), None)
        if line:
            events.append(json.loads(line[5:].strip()))
    return events


async def test_stream_rejects_other_companys_search_set(status_client):
    """남의 검색세트는 스트림이 열리기 전에 403 으로 끝난다."""
    response = await status_client.get("/bid-notices/search-sets/2/status/stream")
    assert response.status_code == 403


async def test_stream_404_when_not_found(status_client):
    response = await status_client.get("/bid-notices/search-sets/999/status/stream")
    assert response.status_code == 404


async def test_stream_emits_status_changes_until_completed(status_client, monkeypatch):
    """상태/진행률이 바뀔 때마다 status 이벤트를 보내고, completed 에서 스트림을 닫는다.

    같은 값이 연속으로 관측되면(3/10 → 3/10) 중복 이벤트를 보내지 않는다.
    """
    sequence = [
        SearchSet(id=1, company_id=1, status="ongoing_second_filter"),
        SearchSet(id=1, company_id=1, status="ongoing_third_filter",
                  progress_current=3, progress_total=10),
        SearchSet(id=1, company_id=1, status="ongoing_third_filter",
                  progress_current=3, progress_total=10),  # 중복 → 스킵 대상
        SearchSet(id=1, company_id=1, status="ongoing_third_filter",
                  progress_current=7, progress_total=10),
        SearchSet(id=1, company_id=1, status="completed",
                  progress_current=10, progress_total=10),
    ]
    calls = {"i": 0}

    async def fake_read_status(search_set_id: int) -> SearchSet:
        item = sequence[min(calls["i"], len(sequence) - 1)]
        calls["i"] += 1
        return item

    monkeypatch.setattr(search_api, "_read_status", fake_read_status)
    monkeypatch.setattr(search_api, "STATUS_POLL_INTERVAL_SECONDS", 0)

    response = await status_client.get("/bid-notices/search-sets/1/status/stream")
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/event-stream")

    events = _parse_sse(response.text)
    statuses = [e["status"] for e in events]
    # 중복 3/10 은 한 번만, completed 에서 종료.
    assert statuses == [
        "ongoing_second_filter",
        "ongoing_third_filter",
        "ongoing_third_filter",
        "completed",
    ]
    third = next(e for e in events if e["status"] == "ongoing_third_filter")
    assert (third["progress_current"], third["progress_total"]) == (3, 10)
    assert events[-1]["type"] == "status"
    assert events[-1]["status"] == "completed"


async def test_stream_reports_error_when_set_disappears(status_client, monkeypatch):
    """소유권 통과 후 세트가 사라지면 error 이벤트로 알리고 종료한다."""

    async def fake_read_status(search_set_id: int) -> SearchSet | None:
        return None

    monkeypatch.setattr(search_api, "_read_status", fake_read_status)
    monkeypatch.setattr(search_api, "STATUS_POLL_INTERVAL_SECONDS", 0)

    response = await status_client.get("/bid-notices/search-sets/1/status/stream")
    assert response.status_code == 200
    events = _parse_sse(response.text)
    assert events[-1]["type"] == "error"
