"""ThirdFilterService 단위 테스트 (DB/LLM 없이).

- LLM: response_model 타입으로 분기하는 FakeLLM
- 채점: evaluation_service_factory 주입으로 EvaluationService 를 통째로 대체
- 검증/요약 단계의 리포지토리: monkeypatch 로 third_filter_service 모듈의
  리포지토리 클래스들을 fake 로 교체
"""

from typing import Any

import pytest

import app.services.third_filter_service as tfs
from app.common.exceptions import AppException
from app.db.models.analysis import AnalysisResult
from app.db.models.bid import BidNotice, Chunk
from app.db.models.company import CompanyProfile, CompanyProject
from app.schemas.third_filter import (
    ChunkFitJudgment,
    FitJudgmentResult,
    NoticeResultIn,
    NoticeSummaryResult,
    RankedChunkIn,
    ThirdFilterRequest,
)
from app.services.third_filter_service import ThirdFilterService

# --------------------------------------------------------------------------- #
# Fakes
# --------------------------------------------------------------------------- #


class FakeSession:
    def __init__(self) -> None:
        self.commits = 0

    async def commit(self) -> None:
        self.commits += 1

    async def flush(self) -> None:
        pass


class FakeSessionCtx:
    def __init__(self, session: FakeSession) -> None:
        self.session = session

    async def __aenter__(self) -> FakeSession:
        return self.session

    async def __aexit__(self, *args) -> bool:
        return False


class FakeLLM:
    """response_model 타입에 따라 canned 응답을 돌려준다."""

    def __init__(self) -> None:
        self.fit_result = FitJudgmentResult(judgments=[])
        self.summary_text = "테스트 요약"

    async def complete_structured(self, *, system: str, user: str, response_model: type) -> Any:
        if response_model is FitJudgmentResult:
            return self.fit_result
        if response_model is NoticeSummaryResult:
            return NoticeSummaryResult(summary=self.summary_text)
        raise AssertionError(f"unexpected response_model: {response_model}")

    async def embed(self, text: str) -> list[float]:
        return [0.0] * 1024


class FakeEvaluationService:
    """bid_notice_id → soft_score 매핑. 값이 AppException 이면 raise."""

    def __init__(self, scores: dict[int, int | AppException]) -> None:
        self.scores = scores

    async def evaluate(self, search_set_id: int, bid_notice_id: int, company_id: int) -> AnalysisResult:
        outcome = self.scores[bid_notice_id]
        if isinstance(outcome, AppException):
            raise outcome
        return AnalysisResult(
            search_set_id=search_set_id, bid_notice_id=bid_notice_id, soft_score=outcome
        )


class _FakeRepoBase:
    def __init__(self, session) -> None:
        self.session = session


class FakeBidNoticeRepository(_FakeRepoBase):
    notices: dict[int, BidNotice] = {}

    async def get(self, bid_notice_id: int) -> BidNotice | None:
        return self.notices.get(bid_notice_id)


class FakeChunkRepository(_FakeRepoBase):
    chunks: dict[int, Chunk] = {}

    async def get(self, chunk_id: int) -> Chunk | None:
        return self.chunks.get(chunk_id)

    async def list_by_bid_notice(self, bid_notice_id: int) -> list[Chunk]:
        return [c for c in self.chunks.values() if c.bid_notice_id == bid_notice_id]


class FakeCompanyProfileRepository(_FakeRepoBase):
    profiles: dict[int, CompanyProfile] = {}

    async def get_by_company_id(self, company_id: int) -> CompanyProfile | None:
        return self.profiles.get(company_id)


class FakeCompanyProjectRepository(_FakeRepoBase):
    projects: dict[int, CompanyProject] = {}

    async def get(self, project_id: int) -> CompanyProject | None:
        return self.projects.get(project_id)


class FakeAnalysisResultRepository(_FakeRepoBase):
    rows: dict[tuple[int, int], AnalysisResult] = {}

    async def add(self, analysis: AnalysisResult) -> AnalysisResult:
        self.rows[(analysis.search_set_id, analysis.bid_notice_id)] = analysis
        return analysis

    async def get_by_search_set_and_notice(
        self, search_set_id: int, bid_notice_id: int
    ) -> AnalysisResult | None:
        return self.rows.get((search_set_id, bid_notice_id))


# --------------------------------------------------------------------------- #
# Fixtures / helpers
# --------------------------------------------------------------------------- #


@pytest.fixture(autouse=True)
def patch_repos(monkeypatch):
    """third_filter_service 모듈이 참조하는 리포지토리 클래스를 fake 로 교체하고
    클래스 레벨 저장소를 테스트마다 초기화한다."""
    monkeypatch.setattr(tfs, "BidNoticeRepository", FakeBidNoticeRepository)
    monkeypatch.setattr(tfs, "ChunkRepository", FakeChunkRepository)
    monkeypatch.setattr(tfs, "CompanyProfileRepository", FakeCompanyProfileRepository)
    monkeypatch.setattr(tfs, "CompanyProjectRepository", FakeCompanyProjectRepository)
    monkeypatch.setattr(tfs, "AnalysisResultRepository", FakeAnalysisResultRepository)
    FakeBidNoticeRepository.notices = {}
    FakeChunkRepository.chunks = {}
    FakeCompanyProfileRepository.profiles = {}
    FakeCompanyProjectRepository.projects = {}
    FakeAnalysisResultRepository.rows = {}


@pytest.fixture
def fake_session() -> FakeSession:
    return FakeSession()


@pytest.fixture
def fake_llm() -> FakeLLM:
    return FakeLLM()


def make_service(fake_session, fake_llm, scores) -> ThirdFilterService:
    eval_service = FakeEvaluationService(scores)
    return ThirdFilterService(
        session_factory=lambda: FakeSessionCtx(fake_session),
        llm=fake_llm,
        evaluation_service_factory=lambda session, llm: eval_service,
    )


def notice_input(bid_notice_id: int, aggregate_score: float) -> NoticeResultIn:
    return NoticeResultIn(
        bid_notice_id=bid_notice_id,
        aggregate_score=aggregate_score,
        ranked_chunks=[
            RankedChunkIn(
                chunk_id=bid_notice_id * 100,
                rank=1,
                score=0.9,
                matched_source="project",
                matched_id=5,
            )
        ],
    )


def seed_notice(bid_notice_id: int) -> None:
    FakeBidNoticeRepository.notices[bid_notice_id] = BidNotice(
        id=bid_notice_id,
        notice_no=f"N-{bid_notice_id}",
        title=f"공고 {bid_notice_id}",
        demand_org="테스트기관",
    )
    FakeChunkRepository.chunks[bid_notice_id * 100] = Chunk(
        id=bid_notice_id * 100,
        bid_notice_id=bid_notice_id,
        chunk_index=0,
        content=f"공고 {bid_notice_id} 청크 내용",
    )
    FakeCompanyProjectRepository.projects[5] = CompanyProject(
        id=5, company_id=1, title="과거 프로젝트", performance="가용성 99.9%"
    )


def fit_judgment(chunk_id: int, **overrides) -> ChunkFitJudgment:
    base = dict(
        chunk_id=chunk_id,
        verdict="fit",
        cited_source="project",
        cited_id=5,
        cited_field="performance",
        reason="유사 실적 확인",
    )
    return ChunkFitJudgment(**{**base, **overrides})


# --------------------------------------------------------------------------- #
# Tests
# --------------------------------------------------------------------------- #


async def test_final_score_sorting_and_top5_truncation(fake_session, fake_llm):
    """final_score 는 soft_score 와 동일하며, 이 기준으로 정렬되고 상위 5개만 반환된다."""
    ids = list(range(1, 7))  # 공고 6건
    for i in ids:
        seed_notice(i)
    # soft_score 가 클수록 final_score 가 크도록: 공고 i 의 soft = i*10
    scores = {i: i * 10 for i in ids}
    service = make_service(fake_session, fake_llm, scores)

    req = ThirdFilterRequest(
        search_set_id=1,
        company_id=1,
        results=[notice_input(i, aggregate_score=0.5) for i in ids],
    )
    res = await service.run(req)

    assert len(res.results) == 5  # 6건 중 상위 5건만
    returned_ids = [r.bid_notice_id for r in res.results]
    assert returned_ids == [6, 5, 4, 3, 2]  # final_score 내림차순
    assert res.results[0].final_score == 60
    assert res.results[0].title == "공고 6"
    assert res.results[0].demand_org == "테스트기관"
    assert res.skipped == []


async def test_aggregate_score_does_not_affect_ranking(fake_session, fake_llm):
    """aggregate_score 는 최종점수 산정에 반영되지 않는다.

    soft_score 가 같으면 aggregate_score 가 아무리 달라도 순위/최종점수가 같아야 한다.
    """
    for i in (1, 2):
        seed_notice(i)
    scores = {1: 50, 2: 50}
    service = make_service(fake_session, fake_llm, scores)

    req = ThirdFilterRequest(
        search_set_id=1,
        company_id=1,
        results=[notice_input(1, aggregate_score=0.01), notice_input(2, aggregate_score=0.99)],
    )
    res = await service.run(req)

    assert res.results[0].final_score == res.results[1].final_score == 50
    # aggregate_score 자체는 참고용으로 응답에 그대로 노출된다.
    aggregate_by_notice = {r.bid_notice_id: r.aggregate_score for r in res.results}
    assert aggregate_by_notice == {1: 0.01, 2: 0.99}


async def test_app_exception_keeps_notice_with_zero_soft_score(fake_session, fake_llm):
    """배점표 미발견(AppException 404)은 soft_score=0(=final_score 최하위)으로 랭킹에 남는다."""
    for i in (1, 2):
        seed_notice(i)
    scores = {
        1: AppException("평가기준표를 찾을 수 없습니다.", status_code=404),
        2: 50,
    }
    service = make_service(fake_session, fake_llm, scores)

    req = ThirdFilterRequest(
        search_set_id=1,
        company_id=1,
        results=[notice_input(1, 0.9), notice_input(2, 0.1)],
    )
    res = await service.run(req)

    assert [r.bid_notice_id for r in res.results] == [2, 1]
    failed = res.results[1]
    assert failed.final_score == 0
    assert len(failed.weaknesses) == 1
    assert "평가기준표를 찾을 수 없습니다" in failed.weaknesses[0].reason
    assert failed.weaknesses[0].chunk_id is None
    assert res.skipped == []


async def test_unexpected_error_goes_to_skipped(fake_session, fake_llm):
    """예상 못한 예외가 난 공고는 skipped 로 빠지고 요청 전체는 성공한다."""
    seed_notice(1)
    scores = {1: 10, 2: RuntimeError}  # 2번은 매핑 타입이 달라 evaluate 내부에서 KeyError 대신 raise

    class Boom(FakeEvaluationService):
        async def evaluate(self, search_set_id, bid_notice_id, company_id):
            if bid_notice_id == 2:
                raise RuntimeError("db down")
            return await super().evaluate(search_set_id, bid_notice_id, company_id)

    eval_service = Boom(scores)
    service = ThirdFilterService(
        session_factory=lambda: FakeSessionCtx(fake_session),
        llm=fake_llm,
        evaluation_service_factory=lambda session, llm: eval_service,
    )

    req = ThirdFilterRequest(
        search_set_id=1,
        company_id=1,
        results=[notice_input(1, 0.5), notice_input(2, 0.5)],
    )
    res = await service.run(req)

    assert [r.bid_notice_id for r in res.results] == [1]
    assert [s.bid_notice_id for s in res.skipped] == [2]


async def test_fit_without_citation_is_corrected_to_unfit(fake_session, fake_llm):
    """fit 인데 cited_source='none' 인 LLM 응답은 unfit 으로 강제 보정된다."""
    seed_notice(1)
    fake_llm.fit_result = FitJudgmentResult(
        judgments=[fit_judgment(100, cited_source="none", cited_id=None, cited_field=None)]
    )
    service = make_service(fake_session, fake_llm, {1: 10})

    req = ThirdFilterRequest(search_set_id=1, company_id=1, results=[notice_input(1, 0.5)])
    res = await service.run(req)

    top = res.results[0]
    assert top.recommend_reason == []
    assert len(top.weaknesses) == 1
    assert top.weaknesses[0].chunk_id == 100


async def test_reasons_and_summary_are_persisted(fake_session, fake_llm):
    """적합/부적합 이유와 요약이 AnalysisResult 에 기록되고 commit 된다."""
    seed_notice(1)
    fake_llm.fit_result = FitJudgmentResult(judgments=[fit_judgment(100)])
    # evaluate 가 저장했을 기존 행을 흉내낸다
    FakeAnalysisResultRepository.rows[(1, 1)] = AnalysisResult(
        search_set_id=1, bid_notice_id=1, soft_score=10
    )
    service = make_service(fake_session, fake_llm, {1: 10})

    req = ThirdFilterRequest(search_set_id=1, company_id=1, results=[notice_input(1, 0.5)])
    res = await service.run(req)

    saved = FakeAnalysisResultRepository.rows[(1, 1)]
    assert saved.recommend_reason == [
        {
            "chunk_id": 100,
            "reason": "유사 실적 확인",
            "cited_source": "project",
            "cited_id": 5,
            "cited_field": "performance",
        }
    ]
    assert saved.weaknesses == []
    assert saved.summary == "테스트 요약"
    assert fake_session.commits >= 1
    assert [r.model_dump() for r in res.results[0].recommend_reason] == saved.recommend_reason


async def test_summary_truncated_to_100_chars(fake_session, fake_llm):
    seed_notice(1)
    fake_llm.summary_text = "가" * 150
    service = make_service(fake_session, fake_llm, {1: 10})

    req = ThirdFilterRequest(search_set_id=1, company_id=1, results=[notice_input(1, 0.5)])
    res = await service.run(req)

    assert len(res.results[0].summary) == 100
