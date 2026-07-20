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
from app.core.config import settings
from app.core.enums import SearchSetStatus
from app.db.models.analysis import AnalysisResult
from app.db.models.bid import BidNotice, Chunk
from app.db.models.company import CompanyProfile, CompanyProject
from app.db.models.search import SearchSet
from app.schemas.third_filter import (
    FitReason,
    NoticeFitAnalysis,
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
    """response_model 타입에 따라 canned 응답을 돌려준다.

    적합성 분석은 공고 1건당 요청 1건이라, 배치 요청 수만큼 fit_analysis 를 복제해 돌려준다.
    batch_calls 에는 (요청 수, model) 을 기록해 배치로 묶였는지/모델이 맞는지 검증한다.
    """

    def __init__(self) -> None:
        self.fit_analysis = NoticeFitAnalysis(recommend_reason=[], weaknesses=[])
        self.summary_text = "테스트 요약"
        self.batch_calls: list[tuple[int, str | None]] = []
        self.fit_prompts: list[str] = []

    async def complete_structured(
        self, *, system: str, user: str, response_model: type, model: str | None = None
    ) -> Any:
        if response_model is NoticeSummaryResult:
            return NoticeSummaryResult(summary=self.summary_text)
        raise AssertionError(f"unexpected response_model: {response_model}")

    async def complete_structured_batch(
        self,
        *,
        requests: list[tuple[str, str]],
        response_model: type,
        model: str | None = None,
    ) -> list[Any]:
        if response_model is NoticeFitAnalysis:
            self.batch_calls.append((len(requests), model))
            self.fit_prompts.extend(user for _, user in requests)
            return [self.fit_analysis.model_copy(deep=True) for _ in requests]
        raise AssertionError(f"unexpected response_model: {response_model}")

    async def embed(self, text: str) -> list[float]:
        return [0.0] * 1024


class FakeEvaluationService:
    """bid_notice_id → soft_score 매핑. 값이 AppException 이면 raise."""

    def __init__(self, scores: dict[int, int | AppException]) -> None:
        self.scores = scores
        self.evaluated: list[int] = []  # 실제 채점된 공고 (후보 컷 검증용)

    async def evaluate(self, search_set_id: int, bid_notice_id: int, company_id: int) -> AnalysisResult:
        self.evaluated.append(bid_notice_id)
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

    async def list_by_company(
        self, company_id: int, limit: int = 20, offset: int = 0
    ) -> list[CompanyProject]:
        rows = [p for p in self.projects.values() if p.company_id == company_id]
        return rows[offset : offset + limit]


class FakeAnalysisResultRepository(_FakeRepoBase):
    rows: dict[tuple[int, int], AnalysisResult] = {}

    async def add(self, analysis: AnalysisResult) -> AnalysisResult:
        self.rows[(analysis.search_set_id, analysis.bid_notice_id)] = analysis
        return analysis

    async def get_by_search_set_and_notice(
        self, search_set_id: int, bid_notice_id: int
    ) -> AnalysisResult | None:
        return self.rows.get((search_set_id, bid_notice_id))


class FakeSearchSetRepository(_FakeRepoBase):
    """SearchSet.status / 진행률 갱신 호출을 기록한다(DB 없이)."""

    sets: dict[int, SearchSet] = {}
    status_history: list[str] = []
    progress_history: list[tuple[int, int]] = []

    async def get(self, search_set_id: int) -> SearchSet | None:
        return self.sets.get(search_set_id)

    async def set_status(
        self, search_set_id: int, status: SearchSetStatus
    ) -> SearchSet | None:
        search_set = self.sets.get(search_set_id)
        if search_set is None:
            return None
        search_set.status = status.value
        self.status_history.append(status.value)
        return search_set

    async def set_progress(
        self, search_set_id: int, current: int, total: int
    ) -> SearchSet | None:
        search_set = self.sets.get(search_set_id)
        if search_set is None:
            return None
        # 실제 리포지토리와 같은 단조 증가 규칙
        search_set.progress_current = (
            0 if current == 0 else max(search_set.progress_current or 0, current)
        )
        search_set.progress_total = total
        self.progress_history.append((current, total))
        return search_set


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
    monkeypatch.setattr(tfs, "SearchSetRepository", FakeSearchSetRepository)
    FakeBidNoticeRepository.notices = {}
    FakeChunkRepository.chunks = {}
    FakeCompanyProfileRepository.profiles = {}
    FakeCompanyProjectRepository.projects = {}
    FakeAnalysisResultRepository.rows = {}
    FakeSearchSetRepository.sets = {1: SearchSet(id=1, company_id=1, title="테스트 검색세트")}
    FakeSearchSetRepository.status_history = []
    FakeSearchSetRepository.progress_history = []


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


def fit_reason(chunk_id: int = 100, **overrides) -> FitReason:
    """seed_notice 가 심는 project#5 를 인용하는 cited 항목 (guard 를 통과하는 형태)."""
    base = dict(
        chunk_id=chunk_id,
        reason="유사 실적 확인",
        grounding="cited",
        cited_source="project",
        cited_id=5,
        cited_field="performance",
    )
    return FitReason(**{**base, **overrides})


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


async def test_run_updates_search_set_status_ongoing_then_completed(fake_session, fake_llm):
    """3차 필터 시작 시 ongoing_third_filter → 상위 5건 확정 시 ongoing_report_generation
    → 끝나면 completed 순으로 검색세트 상태가 바뀐다."""
    seed_notice(1)
    service = make_service(fake_session, fake_llm, {1: 10})

    req = ThirdFilterRequest(
        search_set_id=1, company_id=1, results=[notice_input(1, aggregate_score=0.5)]
    )
    await service.run(req)

    assert tfs.SearchSetRepository.status_history == [
        SearchSetStatus.ONGOING_THIRD_FILTER.value,
        SearchSetStatus.ONGOING_REPORT_GENERATION.value,
        SearchSetStatus.COMPLETED.value,
    ]
    assert tfs.SearchSetRepository.sets[1].status == SearchSetStatus.COMPLETED.value


async def test_progress_advances_to_total_as_notices_are_scored(fake_session, fake_llm):
    """진행률이 0/후보수 로 시작해 공고 채점마다 올라 최종 후보수/후보수 에 도달한다."""
    ids = list(range(1, 13))  # 공고 12건 → 후보 10건
    for i in ids:
        seed_notice(i)
    service = make_service(fake_session, fake_llm, {i: 10 for i in ids})

    req = ThirdFilterRequest(
        search_set_id=1,
        company_id=1,
        results=[notice_input(i, aggregate_score=i / 100) for i in ids],
    )
    await service.run(req)

    history = tfs.SearchSetRepository.progress_history
    assert history[0] == (0, 10)  # 시작 시 0/후보수 로 초기화
    assert [c for c, _ in history] == list(range(0, 11))  # 0,1,2,...,10 단조 증가
    assert all(total == 10 for _, total in history)  # 분모는 후보 수로 고정
    assert tfs.SearchSetRepository.sets[1].progress_current == 10
    assert tfs.SearchSetRepository.sets[1].progress_total == 10


async def test_progress_counts_failed_notices_too(fake_session, fake_llm):
    """채점 실패/불가 공고도 진행률에 세어, 진행률이 중간에 멈춰 보이지 않는다."""
    for i in (1, 2, 3):
        seed_notice(i)
    scores = {
        1: 50,
        2: AppException("평가기준표를 찾을 수 없습니다.", status_code=404),  # 채점 불가
        3: 30,
    }

    class Boom(FakeEvaluationService):
        async def evaluate(self, search_set_id, bid_notice_id, company_id):
            if bid_notice_id == 3:
                raise RuntimeError("db down")  # 예상 못한 오류 → skipped
            return await super().evaluate(search_set_id, bid_notice_id, company_id)

    service = ThirdFilterService(
        session_factory=lambda: FakeSessionCtx(fake_session),
        llm=fake_llm,
        evaluation_service_factory=lambda s, l: Boom(scores),
    )
    req = ThirdFilterRequest(
        search_set_id=1,
        company_id=1,
        results=[notice_input(i, 0.5) for i in (1, 2, 3)],
    )
    res = await service.run(req)

    assert [s.bid_notice_id for s in res.skipped] == [3]  # 3번은 실패했지만
    assert tfs.SearchSetRepository.sets[1].progress_current == 3  # 진행률은 3/3 까지 참
    assert tfs.SearchSetRepository.sets[1].progress_total == 3


async def test_candidate_cut_scores_only_top_aggregate_notices(fake_session, fake_llm):
    """채점은 aggregate_score 상위 CANDIDATE_N 건에만 수행되고, 그 아래는 채점 자체를 건너뛴다."""
    ids = list(range(1, 13))  # 공고 12건 > CANDIDATE_N(10)
    for i in ids:
        seed_notice(i)
    eval_service = FakeEvaluationService({i: 10 for i in ids})
    service = ThirdFilterService(
        session_factory=lambda: FakeSessionCtx(fake_session),
        llm=fake_llm,
        evaluation_service_factory=lambda session, llm: eval_service,
    )

    # 공고 i 의 aggregate_score = i/100 → 상위 10건은 3~12, 하위 2건(1·2)은 컷된다.
    req = ThirdFilterRequest(
        search_set_id=1,
        company_id=1,
        results=[notice_input(i, aggregate_score=i / 100) for i in ids],
    )
    res = await service.run(req)

    assert sorted(eval_service.evaluated) == list(range(3, 13))
    assert len(eval_service.evaluated) == ThirdFilterService.CANDIDATE_N
    assert 1 not in eval_service.evaluated and 2 not in eval_service.evaluated
    # 컷된 공고는 오류가 아니므로 skipped 에도 들어가지 않는다.
    assert res.skipped == []


async def test_candidate_cut_keeps_all_notices_when_under_limit(fake_session, fake_llm):
    """입력이 CANDIDATE_N 이하면 컷 없이 전부 채점한다."""
    ids = list(range(1, 5))  # 공고 4건 < CANDIDATE_N(10)
    for i in ids:
        seed_notice(i)
    eval_service = FakeEvaluationService({i: 10 for i in ids})
    service = ThirdFilterService(
        session_factory=lambda: FakeSessionCtx(fake_session),
        llm=fake_llm,
        evaluation_service_factory=lambda session, llm: eval_service,
    )

    req = ThirdFilterRequest(
        search_set_id=1,
        company_id=1,
        results=[notice_input(i, aggregate_score=0.5) for i in ids],
    )
    await service.run(req)

    assert sorted(eval_service.evaluated) == ids


async def test_ranking_within_candidates_still_uses_soft_score(fake_session, fake_llm):
    """후보 선별은 aggregate_score 로 하지만, 후보 안에서의 순위는 soft_score 로 매긴다."""
    ids = list(range(1, 13))
    for i in ids:
        seed_notice(i)
    # aggregate 는 i 에 비례(상위 10건 = 3~12), soft_score 는 그 역순.
    eval_service = FakeEvaluationService({i: (13 - i) * 10 for i in ids})
    service = ThirdFilterService(
        session_factory=lambda: FakeSessionCtx(fake_session),
        llm=fake_llm,
        evaluation_service_factory=lambda session, llm: eval_service,
    )

    req = ThirdFilterRequest(
        search_set_id=1,
        company_id=1,
        results=[notice_input(i, aggregate_score=i / 100) for i in ids],
    )
    res = await service.run(req)

    # 후보(3~12) 중 soft_score 최상위는 3(=100점), 그 다음 4, 5...
    assert [r.bid_notice_id for r in res.results] == [3, 4, 5, 6, 7]
    assert res.results[0].final_score == 100


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


async def test_cited_without_real_evidence_is_downgraded_to_inferred(fake_session, fake_llm):
    """grounding='cited' 인데 프롬프트에 없던 ID(project#999)를 인용하면 inferred 로 내려간다.

    항목 자체는 남는다 — 관찰은 유효하고 근거 강도만 낮은 것으로 취급한다.
    """
    seed_notice(1)  # project#5 만 심는다
    fake_llm.fit_analysis = NoticeFitAnalysis(
        recommend_reason=[fit_reason(100, cited_id=999)],
        weaknesses=[],
    )
    service = make_service(fake_session, fake_llm, {1: 10})

    req = ThirdFilterRequest(search_set_id=1, company_id=1, results=[notice_input(1, 0.5)])
    res = await service.run(req)

    item = res.results[0].recommend_reason[0]
    assert item.grounding == "inferred"
    assert item.cited_source == "none"
    assert item.cited_id is None
    assert item.cited_field is None
    assert item.reason == "유사 실적 확인"  # 문구는 그대로 남는다


async def test_cited_with_real_evidence_is_kept(fake_session, fake_llm):
    """실제로 프롬프트에 실린 project#5 를 인용하면 cited 그대로 유지된다."""
    seed_notice(1)
    fake_llm.fit_analysis = NoticeFitAnalysis(
        recommend_reason=[fit_reason(100)], weaknesses=[]
    )
    service = make_service(fake_session, fake_llm, {1: 10})

    req = ThirdFilterRequest(search_set_id=1, company_id=1, results=[notice_input(1, 0.5)])
    res = await service.run(req)

    item = res.results[0].recommend_reason[0]
    assert item.grounding == "cited"
    assert (item.cited_source, item.cited_id, item.cited_field) == ("project", 5, "performance")


async def test_fit_items_capped_at_five(fake_session, fake_llm):
    """LLM 이 5개를 넘겨 반환해도 각 목록은 5개로 잘린다."""
    seed_notice(1)
    fake_llm.fit_analysis = NoticeFitAnalysis(
        recommend_reason=[fit_reason(100) for _ in range(8)],
        weaknesses=[fit_reason(100, grounding="inferred", cited_source="none", cited_id=None) for _ in range(7)],
    )
    service = make_service(fake_session, fake_llm, {1: 10})

    req = ThirdFilterRequest(search_set_id=1, company_id=1, results=[notice_input(1, 0.5)])
    res = await service.run(req)

    assert len(res.results[0].recommend_reason) == 5
    assert len(res.results[0].weaknesses) == 5


async def test_fit_analysis_is_one_batch_call_with_fit_model(fake_session, fake_llm):
    """상위 공고 3건이 요청 3건짜리 배치 1회로 묶이고, fit_judgment_model 로 호출된다."""
    for i in (1, 2, 3):
        seed_notice(i)
    service = make_service(fake_session, fake_llm, {1: 30, 2: 20, 3: 10})

    req = ThirdFilterRequest(
        search_set_id=1, company_id=1, results=[notice_input(i, 0.5) for i in (1, 2, 3)]
    )
    await service.run(req)

    assert fake_llm.batch_calls == [(3, settings.fit_judgment_model)]


async def test_fit_prompt_contains_all_company_projects(fake_session, fake_llm):
    """공고에 매칭되지 않은 프로젝트도 프롬프트에 실린다.

    '공고가 요구하는데 회사에 없음'을 판정하려면 전체 목록이 보여야 하고, 매칭된 것만
    보여주면 실제로는 보유한 실적을 없다고 단정하게 된다.
    """
    seed_notice(1)  # ranked_chunks 는 project#5 만 매칭한다
    FakeCompanyProjectRepository.projects[6] = CompanyProject(
        id=6, company_id=1, title="매칭 안 된 프로젝트", performance="처리량 2배"
    )
    service = make_service(fake_session, fake_llm, {1: 10})

    req = ThirdFilterRequest(search_set_id=1, company_id=1, results=[notice_input(1, 0.5)])
    await service.run(req)

    prompt = fake_llm.fit_prompts[0]
    assert "project#5" in prompt
    assert "project#6" in prompt  # 매칭 안 됐어도 실린다
    assert "매칭 안 된 프로젝트" in prompt


async def test_reasons_and_summary_are_persisted(fake_session, fake_llm):
    """적합/부적합 이유와 요약이 AnalysisResult 에 기록되고 commit 된다."""
    seed_notice(1)
    fake_llm.fit_analysis = NoticeFitAnalysis(
        recommend_reason=[fit_reason(100)], weaknesses=[]
    )
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
            "grounding": "cited",
            "cited_source": "project",
            "cited_id": 5,
            "cited_field": "performance",
        }
    ]
    assert saved.weaknesses == []
    assert saved.summary == "테스트 요약"
    assert fake_session.commits >= 1
    assert [r.model_dump() for r in res.results[0].recommend_reason] == saved.recommend_reason


async def test_batch_stage_failure_marks_search_set_failed(fake_session, fake_llm):
    """4-b(적합성 분석 배치 호출) 처럼 여러 공고를 한 번에 처리하는 단계가 통째로 실패하면,
    검색세트가 ongoing_report_generation 에 멈춰있지 않고 failed 로 남아야 한다."""
    seed_notice(1)
    service = make_service(fake_session, fake_llm, {1: 10})

    async def boom(*, requests, response_model, model=None):
        raise RuntimeError("llm batch down")

    fake_llm.complete_structured_batch = boom

    req = ThirdFilterRequest(search_set_id=1, company_id=1, results=[notice_input(1, 0.5)])
    with pytest.raises(RuntimeError):
        await service.run(req)

    assert tfs.SearchSetRepository.sets[1].status == SearchSetStatus.FAILED.value
    assert tfs.SearchSetRepository.status_history[-1] == SearchSetStatus.FAILED.value


async def test_summary_truncated_to_100_chars(fake_session, fake_llm):
    seed_notice(1)
    fake_llm.summary_text = "가" * 150
    service = make_service(fake_session, fake_llm, {1: 10})

    req = ThirdFilterRequest(search_set_id=1, company_id=1, results=[notice_input(1, 0.5)])
    res = await service.run(req)

    assert len(res.results[0].summary) == 100
