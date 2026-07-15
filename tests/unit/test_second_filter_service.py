"""SecondFilterService 단위 테스트 (DB/LLM 없이).

2층 랭킹을 격리해 검증한다:
  - 1층: 타깃(프로필/프로젝트)마다 dense(임베딩) + BM25(텍스트)
  - 2층: 자유형식 메시지 BM25 스티어링(soft 가점)
  - 매칭 타깃은 청크 임베딩과의 코사인 최근접으로 귀속(임베딩 없으면 제외)
  - 도메인 스코프(개요/요구사항) 요청, aggregate_score = 점수 합, 매칭도 내림차순 정렬

실제 pgvector/pg_search SQL 은 통합 실행으로 별도 검증한다.
"""

from __future__ import annotations

import pytest

from app.db.models.bid import Chunk
from app.services import second_filter_service as sfs
from app.services.second_filter_service import RRF_K, SecondFilterService, _Target

PROFILE_EMB = [1.0, 0.0]
PROJECT_EMB = [0.0, 1.0]


def make_chunk(
    chunk_id: int,
    l_topic: str = "요구사항",
    content: str = "내용",
    embedding: list[float] | None = PROFILE_EMB,
) -> Chunk:
    return Chunk(
        id=chunk_id,
        bid_notice_id=1,
        chunk_index=chunk_id,
        content=content,
        chunk_metadata={"l_topic": l_topic, "s_topic": "x"},
        embedding=embedding,
    )


def profile_target(text: str = "") -> _Target:
    return _Target("profile", 1, PROFILE_EMB, text)


def project_target(text: str = "") -> _Target:
    return _Target("project", 5, PROJECT_EMB, text)


class FakeChunkRepo:
    """타깃 임베딩별 dense 결과 + 쿼리 텍스트별 sparse(BM25) 결과를 심어두는 가짜 리포지토리."""

    def __init__(self) -> None:
        self.dense: dict[tuple[float, ...], list[tuple[Chunk, float]]] = {}
        self.sparse_by_query: dict[str, list[tuple[Chunk, float]]] = {}
        self.dense_calls: list[dict] = []
        self.sparse_calls: list[dict] = []

    async def dense_search(self, bid_notice_id, query_embedding, limit=10, l_topics=None):
        self.dense_calls.append({"limit": limit, "l_topics": l_topics})
        return self.dense.get(tuple(query_embedding), [])[:limit]

    async def sparse_search(self, bid_notice_id, query_text, limit=10, l_topics=None):
        self.sparse_calls.append({"query_text": query_text, "l_topics": l_topics})
        return self.sparse_by_query.get(query_text, [])[:limit]


@pytest.fixture(autouse=True)
def no_embedding(monkeypatch):
    """ensure_company_embedded 가 DB/OpenAI 를 건드리지 않게 무력화."""
    async def _noop(session, company_id):
        return 0

    monkeypatch.setattr(sfs.embedding_service, "ensure_company_embedded", _noop)


def make_service() -> tuple[SecondFilterService, FakeChunkRepo]:
    repo = FakeChunkRepo()
    service = SecondFilterService(session=object(), chunk_repo=repo)
    return service, repo


async def test_dense_attribution_and_ranking():
    """1층 dense 만(타깃 텍스트 비움, 메시지 없음): RRF 순위 + 코사인 귀속."""
    service, repo = make_service()
    a = make_chunk(10, embedding=PROFILE_EMB)
    b = make_chunk(11, embedding=PROJECT_EMB)
    c = make_chunk(12, embedding=PROFILE_EMB)
    repo.dense[tuple(PROFILE_EMB)] = [(a, 0.1), (b, 0.2)]  # 프로필: A(0), B(1)
    repo.dense[tuple(PROJECT_EMB)] = [(b, 0.05), (c, 0.3)]  # 프로젝트: B(0), C(1)
    targets = [profile_target(), project_target()]  # text="" → BM25 skip

    ranked = await service._rank_chunks(1, targets, query_text=None, top_k=5)

    ids = [rc.chunk_id for rc in ranked]
    assert ids[0] == 11  # B: 두 dense 리스트에 모두 등장 → 최고 융합점수
    assert set(ids) == {10, 11, 12}
    by_id = {rc.chunk_id: rc for rc in ranked}
    assert by_id[11].matched_source == "project"  # 벡터=프로젝트 → 코사인 귀속
    assert by_id[10].matched_source == "profile"
    assert by_id[12].matched_source == "profile"
    assert by_id[11].score == pytest.approx(
        1 / (RRF_K + 2) + 1 / (RRF_K + 1), abs=1e-6
    )


async def test_domain_topics_requested():
    """dense·1층 BM25·2층 메시지 BM25 모두 개요·요구사항으로 스코프를 요청한다."""
    service, repo = make_service()
    repo.dense[tuple(PROFILE_EMB)] = [(make_chunk(1), 0.1)]
    targets = [profile_target(text="회사 역량 텍스트")]

    await service._rank_chunks(1, targets, query_text="공공 챗봇", top_k=5)

    assert repo.dense_calls[0]["l_topics"] == ["개요", "요구사항"]
    assert all(c["l_topics"] == ["개요", "요구사항"] for c in repo.sparse_calls)
    queries = {c["query_text"] for c in repo.sparse_calls}
    assert queries == {"회사 역량 텍스트", "공공 챗봇"}  # 타깃 텍스트 + 메시지


async def test_target_bm25_introduces_candidate():
    """1층 BM25(타깃 텍스트)에만 걸린 청크도 후보로 합류하고 코사인 귀속된다."""
    service, repo = make_service()
    dense_hit = make_chunk(1, embedding=PROFILE_EMB)
    bm25_hit = make_chunk(2, embedding=PROJECT_EMB)
    repo.dense[tuple(PROFILE_EMB)] = [(dense_hit, 0.1)]
    repo.sparse_by_query["역량"] = [(bm25_hit, 3.0)]
    targets = [profile_target(text="역량"), project_target(text="")]

    ranked = await service._rank_chunks(1, targets, query_text=None, top_k=5)

    assert {rc.chunk_id for rc in ranked} == {1, 2}
    by_id = {rc.chunk_id: rc for rc in ranked}
    assert by_id[2].matched_source == "project"  # 벡터=프로젝트 → 코사인 귀속


async def test_message_steering_boosts_score():
    """2층 메시지 BM25 는 dense 로 찾은 청크의 융합점수를 끌어올린다."""
    service, repo = make_service()
    hit = make_chunk(1, embedding=PROFILE_EMB)
    repo.dense[tuple(PROFILE_EMB)] = [(hit, 0.1)]
    repo.sparse_by_query["강조어"] = [(hit, 7.0)]
    targets = [profile_target(text="")]

    ranked = await service._rank_chunks(1, targets, query_text="강조어", top_k=5)

    # dense rank0(1/(K+1)) + 메시지 BM25 rank0(1/(K+1))
    assert ranked[0].score == pytest.approx(2 / (RRF_K + 1), abs=1e-6)


async def test_chunk_without_embedding_excluded():
    """임베딩 없는 청크는 타깃 귀속 불가라 랭킹에서 제외한다."""
    service, repo = make_service()
    hit = make_chunk(1, embedding=PROFILE_EMB)
    no_emb = make_chunk(2, embedding=None)
    repo.dense[tuple(PROFILE_EMB)] = [(hit, 0.1)]
    repo.sparse_by_query["쿼리"] = [(no_emb, 9.0), (hit, 5.0)]
    targets = [profile_target(text="")]

    ranked = await service._rank_chunks(1, targets, query_text="쿼리", top_k=5)

    assert {rc.chunk_id for rc in ranked} == {1}  # 임베딩 없는 2 는 제외


async def test_top_k_limits_results():
    service, repo = make_service()
    repo.dense[tuple(PROFILE_EMB)] = [(make_chunk(i), 0.1 * i) for i in range(1, 8)]
    targets = [profile_target()]

    ranked = await service._rank_chunks(1, targets, query_text=None, top_k=3)

    assert len(ranked) == 3
    assert [rc.rank for rc in ranked] == [1, 2, 3]


async def test_run_aggregate_and_sort(monkeypatch):
    """공고별 aggregate_score = 청크 점수 합, 매칭도 내림차순 정렬."""
    service, repo = make_service()

    async def fake_targets(company_id):
        return [profile_target(text="t")]

    monkeypatch.setattr(service, "_load_targets", fake_targets)

    async def fake_rank(bid_notice_id, targets, query_text, top_k):
        from app.schemas.second_filter import RankedChunk

        if bid_notice_id == 1:
            return [
                RankedChunk(chunk_id=1, rank=1, score=0.3, matched_source="profile", matched_id=1),
                RankedChunk(chunk_id=2, rank=2, score=0.2, matched_source="profile", matched_id=1),
            ]
        return [
            RankedChunk(chunk_id=3, rank=1, score=0.1, matched_source="profile", matched_id=1)
        ]

    monkeypatch.setattr(service, "_rank_chunks", fake_rank)

    result = await service.run(
        search_set_id=7, company_id=1, bid_notice_ids=[2, 1], query_text=None
    )

    assert result.search_set_id == 7
    assert [r.bid_notice_id for r in result.results] == [1, 2]  # 0.5 > 0.1
    assert result.results[0].aggregate_score == pytest.approx(0.5)
    assert result.results[1].aggregate_score == pytest.approx(0.1)


async def test_run_no_targets_returns_empty(monkeypatch):
    """임베딩된 프로필/프로젝트가 없으면 빈 랭킹 + 매칭도 0."""
    service, repo = make_service()

    async def no_targets(company_id):
        return []

    monkeypatch.setattr(service, "_load_targets", no_targets)

    result = await service.run(
        search_set_id=1, company_id=1, bid_notice_ids=[1, 2], query_text="쿼리"
    )

    assert [r.bid_notice_id for r in result.results] == [1, 2]
    assert all(r.aggregate_score == 0.0 for r in result.results)
    assert all(r.ranked_chunks == [] for r in result.results)
