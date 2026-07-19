"""검색 오케스트레이션의 임베딩 호출 및 상태 전이 단위 테스트."""

import pytest

from app.common.exceptions import AppException
from app.core.enums import SearchSetStatus
from app.db.models.search import SearchSet
from app.schemas.search import BidSearchRequest
from app.schemas.second_filter import SecondFilterResult
from app.services import search_service


class FakeSession:
    def __init__(self, search_set: SearchSet) -> None:
        self.search_set = search_set
        self.commits = 0
        self.rollbacks = 0

    def add(self, entity) -> None:
        if isinstance(entity, SearchSet):
            self.search_set = entity

    async def commit(self) -> None:
        self.commits += 1

    async def rollback(self) -> None:
        self.rollbacks += 1

    async def get(self, model, entity_id):
        if model is SearchSet and self.search_set.id == entity_id:
            return self.search_set
        return None


async def _stub_search_session(session, company_id, request):
    return session.search_set


async def _no_notices(session, filters):
    return []


class FakeSecondFilterService:
    calls = []

    def __init__(self, session) -> None:
        self.session = session

    async def run(
        self,
        search_set_id,
        company_id,
        bid_notice_ids,
        query_text,
        candidate_k,
        final_k,
    ):
        self.calls.append((candidate_k, final_k))
        return SecondFilterResult(
            search_set_id=search_set_id,
            company_id=company_id,
            results=[],
        )


async def test_search_embeds_once_and_keeps_ongoing_until_third_filter(monkeypatch):
    search_set = SearchSet(id=7, company_id=1, title="검색")
    session = FakeSession(search_set)
    embed_calls = 0
    FakeSecondFilterService.calls.clear()

    async def embed_once(session, company_id):
        nonlocal embed_calls
        embed_calls += 1
        return 2

    monkeypatch.setattr(search_service, "create_search_session", _stub_search_session)
    monkeypatch.setattr(search_service, "hard_filter_notices", _no_notices)
    monkeypatch.setattr(
        search_service.embedding_service, "ensure_company_embedded", embed_once
    )
    monkeypatch.setattr(
        search_service, "SecondFilterService", FakeSecondFilterService
    )

    result = await search_service.search_bid_notices(
        session, company_id=1, request=BidSearchRequest()
    )

    assert embed_calls == 1
    assert FakeSecondFilterService.calls == [(50, 10)]
    assert result.search_set_id == 7
    assert search_set.status == SearchSetStatus.ONGOING_SECOND_FILTER.value
    assert search_set.failure_reason is None


async def test_search_marks_failed_when_company_inputs_are_not_ready(monkeypatch):
    search_set = SearchSet(id=8, company_id=1, title="검색")
    session = FakeSession(search_set)

    async def fail_embedding(session, company_id):
        raise AppException("성공 프로젝트를 하나 이상 작성해 주세요.", status_code=409)

    monkeypatch.setattr(search_service, "create_search_session", _stub_search_session)
    monkeypatch.setattr(
        search_service.embedding_service, "ensure_company_embedded", fail_embedding
    )

    with pytest.raises(AppException, match="성공 프로젝트"):
        await search_service.search_bid_notices(
            session, company_id=1, request=BidSearchRequest()
        )

    assert session.rollbacks == 1
    assert search_set.status == SearchSetStatus.FAILED.value
    assert search_set.failure_reason == "성공 프로젝트를 하나 이상 작성해 주세요."
