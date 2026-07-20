"""3차 필터 오케스트레이션.

흐름:
1. aggregate_score(2차 매칭도) 내림차순 상위 CANDIDATE_N 건으로 채점 후보를 좁힌다
2. 후보 공고를 EvaluationService.evaluate 로 배점표 채점 (공고 간 병렬, 공고별 독립 세션).
   채점 끝난 공고 수를 진행률(progress_current/total)로 기록해 프론트 폴링에 내려준다
3. final_score(= soft_score) 내림차순 정렬 → 상위 TOP_N 선별
4. 상위 공고만 (a) 공고 청크 전체 ↔ 회사 프로필/프로젝트 전체 적합성 LLM 분석
   (공고 1건당 요청 1건을 상위 5건 묶어 배치 전송, recommend_reason/weaknesses 각 최대 5개)
   (b) 공고 내용 100자 요약 을 수행하고 AnalysisResult(recommend_reason/weaknesses/summary)에 저장
   → 이 단계 진입 시 검색세트 상태를 ongoing_report_generation 으로 바꿔 프론트에 구분해 보여준다
5. 상위 공고 목록 + 처리 제외(skipped) 목록 반환

적합성 분석의 근거 강도: 각 항목은 grounding='cited'(프로필/프로젝트 필드 인용) 또는
'inferred'(정황 추론)로 구분된다. LLM 이 인용했다고 답해도 그 ID 가 프롬프트에 실제로 실린
근거가 아니면 _guard_fit_analysis 가 inferred 로 내린다 — cited 라벨이 "정말 그 필드에
적혀 있다"는 뜻을 유지해야 프론트/사용자가 근거를 신뢰할 수 있다.

aggregate_score 의 용도: 1단계 후보 선별에만 쓰고, 최종점수(final_score) 산정에는 쓰지 않는다.
2차 필터가 이미 반영한 매칭도라 점수로 다시 더하면 이중 계산이 되지만, 어느 공고를 채점할지
고르는 사전 지표로는 유효하다. 응답에는 참고 정보로 그대로 포함한다.

동시성: SQLAlchemy AsyncSession 은 동시 쿼리를 허용하지 않으므로,
공고 간 병렬화는 공고마다 session_factory 로 새 세션을 열어 처리한다.
"""

from __future__ import annotations

import asyncio
import enum
import logging

from sqlmodel.ext.asyncio.session import AsyncSession

from app.common.exceptions import AppException
from app.core.config import settings
from app.core.enums import SearchSetStatus
from app.db.models.analysis import AnalysisResult
from app.db.repositories.analysis_repository import AnalysisResultRepository
from app.db.repositories.bid_notice_repository import BidNoticeRepository
from app.db.repositories.chunk_repository import ChunkRepository
from app.db.repositories.company_repository import CompanyProfileRepository, CompanyProjectRepository
from app.db.repositories.eval_criteria_reference_repository import EvalCriteriaReferenceRepository
from app.db.repositories.search_set_repository import SearchSetRepository
from app.llm.base import LLMProvider
from app.schemas.third_filter import (
    FitReason,
    NoticeFitAnalysis,
    NoticeResultIn,
    NoticeSummaryResult,
    SkippedNotice,
    ThirdFilterNoticeRead,
    ThirdFilterRequest,
    ThirdFilterResponse,
)
from app.services.evaluation_service import EvaluationService

logger = logging.getLogger(__name__)

_FIT_ANALYSIS_SYSTEM_PROMPT = (
    "너는 입찰공고 RFP 를 읽고, 이 회사가 해당 공고에 참여할 만한지 분석하는 심사관이다.\n"
    "[공고] 의 청크 전체와 [회사 프로필]·[회사 프로젝트] 전체를 견줘서 "
    "recommend_reason(참여할 만한 이유) 과 weaknesses(불리하거나 부족한 점) 를 "
    "각각 최대 5개씩 뽑아라.\n\n"
    "각 항목에는 grounding 을 반드시 표시한다:\n"
    "- grounding='cited': 프로필/프로젝트의 특정 필드로 뒷받침되는 항목. 이때 "
    "cited_source('profile'/'project'), cited_id, cited_field 에 실제로 존재하는 값을 인용하고, "
    "근거가 된 공고 청크가 있으면 chunk_id 도 채운다.\n"
    "- grounding='inferred': 인용할 필드는 없지만 공고 요구사항과 회사 정보를 견줘 도출한 항목. "
    "cited_source='none' 이고 cited_id/cited_field 는 null 이다.\n\n"
    "규칙:\n"
    "1. 없는 실적·자격·기술을 지어내지 마라. 프로필/프로젝트에 적히지 않은 내용을 회사가 "
    "보유한 것처럼 쓰면 안 된다. 인용할 게 없으면 grounding='inferred' 로 쓰고, "
    "그것도 근거가 없으면 항목을 만들지 말고 5개보다 적게 반환하라.\n"
    "2. cited_id 는 입력에 실제로 등장한 profile#N/project#N 의 N 만 쓴다. "
    "cited_field 도 입력에 등장한 필드명만 쓴다.\n"
    "3. weaknesses 는 '요구사항 대비 부재'에서 정직하게 도출하라. 공고가 요구하는데 "
    "프로필·프로젝트 어디에도 없는 것은 그 자체로 유효한 약점이며 grounding='inferred' 다.\n"
    "4. 도메인·기술이 표면적으로만 겹치는 것은 recommend_reason 이 아니다.\n"
    "5. reason 은 한국어 1~2문장으로 쓴다.\n\n"
    "예시 (recommend_reason, cited):\n"
    "공고에 '학사행정시스템 고도화. Java/Spring 기반 웹 개발 경험 필수'(chunk_id=101) 가 있고 "
    "project#7: title='OO대학교 학사시스템 구축', tech_stack='Java, Spring Boot' 가 있을 때\n"
    "→ grounding='cited', cited_source='project', cited_id=7, cited_field='tech_stack', "
    "chunk_id=101, reason='요구 기술(Java/Spring)과 동일 도메인(학사시스템) 수행 실적을 "
    "project#7 에서 보유하고 있음.'\n\n"
    "예시 (weakness, inferred):\n"
    "공고에 'CC인증 및 보안관제 전문업체 지정 필수'(chunk_id=202) 가 있는데 프로필·프로젝트에 "
    "보안관제 관련 항목이 전혀 없을 때\n"
    "→ grounding='inferred', cited_source='none', cited_id=null, cited_field=null, "
    "chunk_id=202, reason='공고가 요구하는 보안관제 전문업체 지정·CC인증을 뒷받침하는 "
    "실적이나 자격이 회사 정보에 없음.'"
)

_FIT_ANALYSIS_MAX_ITEMS = 5
# 적합성 분석 프롬프트에 넣을 회사 프로젝트 상한. "공고가 요구하는데 회사에 없음"을 판정하려면
# 매칭된 것만이 아니라 전체 목록이 보여야 해서 리포지토리 기본 limit(20)보다 넉넉히 잡는다.
_FIT_ANALYSIS_MAX_PROJECTS = 100

_SUMMARY_SYSTEM_PROMPT = (
    "너는 공공입찰 공고 요약 어시스턴트다. 주어진 RFP 본문을 100자 이내 한국어 한 문장으로 "
    "요약하라. 사업명·발주기관·핵심 과업만 담아라."
)

_SUMMARY_INPUT_MAX_CHARS = 6000
_SUMMARY_MAX_CHARS = 100


def _fmt(value: object) -> str:
    """프롬프트에 넣을 값 표현.

    (str, Enum) 혼합 enum 도 파이썬 3.11+ 에서는 f-string 이 'CreditRating.A_PLUS' 처럼
    찍혀서 LLM 이 실제 등급('A+')을 못 읽는다. enum 은 값으로 풀어서 넣는다.
    """
    if isinstance(value, enum.Enum):
        return str(value.value)
    return str(value)


def _default_evaluation_service_factory(session: AsyncSession, llm: LLMProvider) -> EvaluationService:
    return EvaluationService(
        session=session,
        bid_notice_repo=BidNoticeRepository(session),
        chunk_repo=ChunkRepository(session),
        analysis_repo=AnalysisResultRepository(session),
        search_set_repo=SearchSetRepository(session),
        eval_ref_repo=EvalCriteriaReferenceRepository(session),
        llm=llm,
    )


class _FitPrompt:
    """4-a(프롬프트 구성) 결과를 4-b(배치 호출)로 넘기기 위한 내부 홀더.

    profile_id/project_ids 는 프롬프트에 실제로 실린 근거 ID 다. LLM 이 인용했다고 답한
    cited_id 가 여기 있는지 대조해서, 없는 ID 를 지어낸 인용을 걸러낸다.
    """

    def __init__(
        self,
        bid_notice_id: int,
        prompt: str,
        profile_id: int | None,
        project_ids: set[int],
    ) -> None:
        self.bid_notice_id = bid_notice_id
        self.prompt = prompt
        self.profile_id = profile_id
        self.project_ids = project_ids


class _ScoredNotice:
    """1단계(채점) 결과를 2·3단계로 넘기기 위한 내부 홀더."""

    def __init__(self, item: NoticeResultIn, soft_score: int, note: str | None = None) -> None:
        self.item = item
        self.soft_score = soft_score
        self.note = note  # 배점표 미발견 등으로 soft_score=0 처리된 사유

    @property
    def final_score(self) -> int:
        """최종점수 = soft_score. aggregate_score 는 최종점수 산정에 반영하지 않는다."""
        return self.soft_score


class ThirdFilterService:
    TOP_N = 5
    # 배점표 채점 대상 후보 수. 채점은 공고당 LLM 호출이 수십 회로 가장 비싼 단계인데
    # 최종 반환은 TOP_N(5) 건뿐이라, aggregate_score 상위 이만큼만 채점한다.
    # TOP_N 보다 넉넉히 잡아 aggregate_score 와 soft_score 의 순위 차이를 흡수한다.
    CANDIDATE_N = 10
    MAX_CONCURRENT_NOTICES = 3  # 공고 간 병렬 처리 상한 (LLM/DB 부하 제한)

    def __init__(
        self,
        session_factory,
        llm: LLMProvider,
        evaluation_service_factory=_default_evaluation_service_factory,
    ) -> None:
        self.session_factory = session_factory
        self.llm = llm
        self.evaluation_service_factory = evaluation_service_factory
        self._semaphore = asyncio.Semaphore(self.MAX_CONCURRENT_NOTICES)
        # 채점이 끝난 공고 수(진행률 폴링용). 서비스는 요청마다 새로 만들어지고 asyncio 는
        # 단일 스레드라, 이 카운터는 await 없이 증가시키는 한 경쟁 없이 안전하다.
        self._completed = 0

    # ------------------------------------------------------------------ #
    # 전체 오케스트레이션
    # ------------------------------------------------------------------ #

    async def run(self, req: ThirdFilterRequest) -> ThirdFilterResponse:
        """오케스트레이션 진입점.

        공고 1건 단위 처리(_evaluate_notice/_summarize_and_save)는 이미 내부에서
        개별 실패를 흡수하지만, _build_fit_prompt 의 gather 나 _batch_analyze_fit 의
        배치 LLM 호출처럼 여러 공고를 한 번에 묶어 처리하는 단계는 예외 가드가 없다.
        이 단계에서 예외가 나면 검색세트가 ONGOING_THIRD_FILTER/ONGOING_REPORT_GENERATION
        에 멈춘 채로 남아 프론트가 영원히 폴링하게 되므로, 여기서 잡아 FAILED 로 남기고
        재전파한다.
        """
        try:
            return await self._run(req)
        except Exception:
            logger.exception(
                "[3차] 처리 중 복구 불가능한 오류 발생: search_set=%s", req.search_set_id
            )
            await self._set_search_set_status(req.search_set_id, SearchSetStatus.FAILED)
            raise

    async def _run(self, req: ThirdFilterRequest) -> ThirdFilterResponse:
        skipped: list[SkippedNotice] = []
        self._completed = 0

        # 1단계: aggregate_score 상위 CANDIDATE_N 건만 채점 후보로 좁힌다.
        # 진행률의 분모가 후보 수라서, 상태를 진행중으로 바꾸기 전에 먼저 확정한다.
        candidates = sorted(req.results, key=lambda r: r.aggregate_score, reverse=True)[
            : self.CANDIDATE_N
        ]

        # 3차 필터 시작 → 상태를 진행중으로, 진행률을 0/후보수 로 초기화(폴링용).
        await self._set_search_set_status(
            req.search_set_id, SearchSetStatus.ONGOING_THIRD_FILTER
        )
        await self._set_progress(req.search_set_id, 0, len(candidates))
        logger.info(
            "[3차] 시작 search_set=%s | 입력 %d건 → 채점 후보 %d건 (aggregate_score 상위)",
            req.search_set_id,
            len(req.results),
            len(candidates),
        )

        # 2단계: 후보 공고 배점표 채점 (공고별 독립 세션으로 병렬)
        outcomes = await asyncio.gather(
            *[
                self._evaluate_notice(req, item, i, len(candidates))
                for i, item in enumerate(candidates, start=1)
            ]
        )
        scored: list[_ScoredNotice] = []
        for outcome in outcomes:
            if isinstance(outcome, SkippedNotice):
                skipped.append(outcome)
            else:
                scored.append(outcome)

        # 3단계: 최종점수(=soft_score) 내림차순 상위 TOP_N
        scored.sort(key=lambda s: s.final_score, reverse=True)
        top = scored[: self.TOP_N]

        # 4단계: 상위 공고만 적합성 분석 + 요약 + AnalysisResult 저장
        # 상위 TOP_N 이 확정된 시점부터는 "무엇을 채점 중인지"가 아니라 "리포트를 작성 중"이라
        # 프론트에 다른 문구를 보여줄 수 있도록 상태를 분리한다.
        await self._set_search_set_status(
            req.search_set_id, SearchSetStatus.ONGOING_REPORT_GENERATION
        )
        logger.info(
            "[3차] 채점 완료 → 상위 %d건 LLM 검증/요약 단계 진입 (notice=%s)",
            len(top),
            [s.item.bid_notice_id for s in top],
        )
        # 4-a: 공고별 적합성 분석 프롬프트 구성(DB 읽기만, 공고마다 독립 세션이라 병렬 안전)
        fit_prompts = await asyncio.gather(
            *[self._build_fit_prompt(req, s.item) for s in top]
        )
        # 4-b: 상위 TOP_N 건을 한 번의 배치 호출로 묶어 적합성 분석(공고 1건당 요청 1건)
        fit_analyses = await self._batch_analyze_fit(list(fit_prompts))
        # 4-c: 공고별 요약 + AnalysisResult 저장
        verified = await asyncio.gather(
            *[
                self._summarize_and_save(req, s, fit)
                for s, fit in zip(top, fit_analyses)
            ]
        )
        results: list[ThirdFilterNoticeRead] = []
        for item in verified:
            if isinstance(item, SkippedNotice):
                skipped.append(item)
            else:
                results.append(item)

        # 3차 필터 완료 → 검색세트 상태를 완료로 갱신(폴링 종료 신호).
        await self._set_search_set_status(req.search_set_id, SearchSetStatus.COMPLETED)

        return ThirdFilterResponse(results=results, skipped=skipped)

    async def _set_search_set_status(
        self, search_set_id: int, status: SearchSetStatus
    ) -> None:
        async with self.session_factory() as session:
            await SearchSetRepository(session).set_status(search_set_id, status)

    async def _set_progress(self, search_set_id: int, current: int, total: int) -> None:
        """진행률을 기록한다. 표시용이라 실패해도 채점 파이프라인을 멈추지 않는다."""
        try:
            async with self.session_factory() as session:
                await SearchSetRepository(session).set_progress(
                    search_set_id, current, total
                )
        except Exception:
            logger.warning(
                "진행률 갱신 실패 (무시하고 계속): search_set_id=%s %s/%s",
                search_set_id,
                current,
                total,
                exc_info=True,
            )

    # ------------------------------------------------------------------ #
    # 2단계: 공고 1건 채점
    # ------------------------------------------------------------------ #

    async def _evaluate_notice(
        self, req: ThirdFilterRequest, item: NoticeResultIn, index: int, total: int
    ) -> _ScoredNotice | SkippedNotice:
        # 세마포어 안에서 로그를 찍어야 실제 분석이 시작되는 시점과 일치한다
        # (동시 MAX_CONCURRENT_NOTICES 건만 진행하므로 나머지는 여기서 대기한다).
        async with self._semaphore:
            logger.info(
                "[채점] 공고 분석 시작 (%d/%d) notice=%s aggregate=%.4f",
                index,
                total,
                item.bid_notice_id,
                item.aggregate_score,
            )
            try:
                async with self.session_factory() as session:
                    service = self.evaluation_service_factory(session, self.llm)
                    analysis = await service.evaluate(
                        search_set_id=req.search_set_id,
                        bid_notice_id=item.bid_notice_id,
                        company_id=req.company_id,
                    )
                soft_score = analysis.soft_score or 0
                logger.info(
                    "[채점] 공고 분석 완료 (%d/%d) notice=%s soft_score=%s",
                    index,
                    total,
                    item.bid_notice_id,
                    soft_score,
                )
                return _ScoredNotice(item, soft_score=soft_score)
            except AppException as e:
                # 배점표 미발견(404) 등은 부적격이 아니라 '배점표 가점 없음'으로 취급해
                # soft_score=0(=final_score 최하위)으로 랭킹에는 남긴다(skipped 로 빠뜨리지 않음).
                logger.info(
                    "[채점] 공고 채점 불가 (%d/%d) notice=%s soft_score=0 사유=%s",
                    index,
                    total,
                    item.bid_notice_id,
                    e.message,
                )
                return _ScoredNotice(item, soft_score=0, note=e.message)
            except Exception:
                logger.exception("공고 채점 실패: bid_notice_id=%s", item.bid_notice_id)
                return SkippedNotice(
                    bid_notice_id=item.bid_notice_id, reason="채점 중 오류가 발생했습니다."
                )
            finally:
                # 성공/채점불가/오류 어느 쪽이든 이 공고는 처리가 끝났다. 셋 다 세어야
                # 진행률이 끝까지 차오른다(오류 난 공고에서 멈춰 보이지 않게).
                self._completed += 1
                await self._set_progress(req.search_set_id, self._completed, total)

    # ------------------------------------------------------------------ #
    # 4단계: 상위 TOP_N(5) 공고 적합성 분석 + 요약 + 저장
    #   4-a _build_fit_prompt   공고별 프롬프트 구성 (DB 읽기, 공고마다 독립 세션으로 병렬)
    #   4-b _batch_analyze_fit  상위 TOP_N 건을 한 번의 배치 호출로 (공고 1건당 요청 1건)
    #   4-c _summarize_and_save 공고별 요약 + AnalysisResult 저장
    #   4-a/4-c 는 공고 1건 단위, 4-b 만 전체를 묶는다.
    # ------------------------------------------------------------------ #

    async def _build_fit_prompt(
        self, req: ThirdFilterRequest, item: NoticeResultIn
    ) -> _FitPrompt | None:
        """공고 1건의 청크 전체 + 회사 프로필/프로젝트 전체를 한 프롬프트로 묶는다.

        프로젝트는 이 공고에 매칭된 것만이 아니라 회사의 전체 목록을 넣는다. weaknesses 는
        "공고가 요구하는데 회사에 없음"에서 나오는데, 매칭된 일부만 보여주면 실제로는 보유한
        실적을 없다고 단정하게 된다.

        청크를 하나도 읽지 못하면(내용 없음/삭제) None 을 돌려 이 공고는 LLM 요청에서 뺀다.
        """
        async with self._semaphore:
            async with self.session_factory() as session:
                chunk_repo = ChunkRepository(session)
                profile_repo = CompanyProfileRepository(session)
                project_repo = CompanyProjectRepository(session)

                # 2차 필터가 각 청크에 붙여준 매칭 근거를 참고 정보로 표시한다.
                matched_by_chunk = {
                    rc.chunk_id: f"{rc.matched_source}#{rc.matched_id}" for rc in item.ranked_chunks
                }
                chunk_lines: list[str] = []
                for rc in item.ranked_chunks:
                    chunk = await chunk_repo.get(rc.chunk_id)
                    if chunk is None or not chunk.content:
                        continue
                    chunk_lines.append(
                        f"- chunk_id={rc.chunk_id} (rank={rc.rank}, score={rc.score:.4f}, "
                        f"2차필터 매칭={matched_by_chunk[rc.chunk_id]})\n"
                        f"  {chunk.content}"
                    )
                if not chunk_lines:
                    return None

                profile = await profile_repo.get_by_company_id(req.company_id)
                profile_text = (
                    f"profile#{profile.id}: company_scale={_fmt(profile.company_scale)}, "
                    f"target_techs={_fmt(profile.target_techs)}, "
                    f"offered_solutions={_fmt(profile.offered_solutions)}, "
                    f"strengths_diff={_fmt(profile.strengths_diff)}, "
                    f"credit_rating={_fmt(profile.credit_rating)}, "
                    f"sp_grade={_fmt(profile.sp_grade)}"
                    if profile
                    else "(등록된 프로필 없음)"
                )

                projects = await project_repo.list_by_company(
                    req.company_id, limit=_FIT_ANALYSIS_MAX_PROJECTS
                )
                projects_text = (
                    "\n".join(
                        f"project#{p.id}: title={_fmt(p.title)}, domain={_fmt(p.domain)}, "
                        f"tech_stack={_fmt(p.tech_stack)}, "
                        f"develop_features={_fmt(p.develop_features)}, "
                        f"content={_fmt(p.content)}, performance={_fmt(p.performance)}"
                        for p in projects
                    )
                    or "(등록된 프로젝트 없음)"
                )

                # 인용 검증용 ID 는 세션이 살아 있는 동안 뽑아둔다. 세션이 닫히면 ORM 인스턴스가
                # detach 되어 속성 접근이 불안정해진다.
                profile_id = profile.id if profile else None
                project_ids = {p.id for p in projects if p.id is not None}

        prompt = (
            f"[공고] bid_notice_id={item.bid_notice_id}\n"
            f"공고 청크(2차 필터가 뽑은 상위 매칭 청크):\n" + "\n".join(chunk_lines) + "\n\n"
            f"[회사 프로필]\n{profile_text}\n\n"
            f"[회사 프로젝트] (회사가 보유한 전체 실적 목록. 여기에 없는 실적은 회사에 없는 것이다)\n"
            f"{projects_text}"
        )
        return _FitPrompt(
            bid_notice_id=item.bid_notice_id,
            prompt=prompt,
            profile_id=profile_id,
            project_ids=project_ids,
        )

    async def _batch_analyze_fit(
        self, prompts: list[_FitPrompt | None]
    ) -> list[NoticeFitAnalysis | None]:
        """상위 공고들의 적합성 분석을 한 번의 배치 호출로 묶어 전송한다(공고 1건당 요청 1건).

        청크가 없어 프롬프트를 못 만든 공고는 요청에서 빼고 결과 자리도 None 으로 둔다.
        배점표 채점(llm_model)과 달리 공고 전체를 읽는 무거운 판단이라 fit_judgment_model 을 쓴다.
        """
        askable = [(i, p) for i, p in enumerate(prompts) if p is not None]
        if not askable:
            return [None] * len(prompts)

        logger.info(
            "[검증] 상위 %d건 적합성 분석 배치 요청 전송 (model=%s, notice=%s)",
            len(askable),
            settings.fit_judgment_model,
            [p.bid_notice_id for _, p in askable],
        )
        analyses = await self.llm.complete_structured_batch(
            requests=[(_FIT_ANALYSIS_SYSTEM_PROMPT, p.prompt) for _, p in askable],
            response_model=NoticeFitAnalysis,
            model=settings.fit_judgment_model,
        )

        out: list[NoticeFitAnalysis | None] = [None] * len(prompts)
        for (index, fit_prompt), analysis in zip(askable, analyses):
            out[index] = self._guard_fit_analysis(analysis, fit_prompt)
        return out

    @staticmethod
    def _guard_fit_analysis(analysis: NoticeFitAnalysis, fit_prompt: _FitPrompt) -> NoticeFitAnalysis:
        """방어적 가드: grounding='cited' 인데 실제로 인용한 게 없거나, 입력에 없던
        프로필/프로젝트 ID 를 가리키면 'inferred' 로 내린다.

        이 가드가 있어야 cited 라벨이 "정말 그 필드에 적혀 있다"는 뜻을 유지한다. 항목 자체를
        버리지는 않는다 — 관찰은 유효하고 근거 강도만 낮은 경우가 대부분이라, 지우는 대신
        inferred 로 표시해 프론트가 구분해 보여주게 한다.
        """

        def cites_real_evidence(r: FitReason) -> bool:
            if r.cited_source == "profile":
                return r.cited_id is not None and r.cited_id == fit_prompt.profile_id
            if r.cited_source == "project":
                return r.cited_id is not None and r.cited_id in fit_prompt.project_ids
            return False

        def fix(items: list[FitReason]) -> list[FitReason]:
            fixed: list[FitReason] = []
            for r in items[:_FIT_ANALYSIS_MAX_ITEMS]:
                if r.grounding == "cited" and not cites_real_evidence(r):
                    logger.warning(
                        "적합성 분석 인용 검증 실패 → inferred 로 보정: notice=%s cited=%s#%s",
                        fit_prompt.bid_notice_id,
                        r.cited_source,
                        r.cited_id,
                    )
                    fixed.append(
                        r.model_copy(
                            update={
                                "grounding": "inferred",
                                "cited_source": "none",
                                "cited_id": None,
                                "cited_field": None,
                            }
                        )
                    )
                else:
                    fixed.append(r)
            return fixed

        return analysis.model_copy(
            update={
                "recommend_reason": fix(analysis.recommend_reason),
                "weaknesses": fix(analysis.weaknesses),
            }
        )

    async def _summarize_and_save(
        self,
        req: ThirdFilterRequest,
        scored: _ScoredNotice,
        fit: NoticeFitAnalysis | None,
    ) -> ThirdFilterNoticeRead | SkippedNotice:
        bid_notice_id = scored.item.bid_notice_id
        async with self._semaphore:
            logger.info(
                "[검증] 상위 공고 요약/저장 notice=%s final_score=%s",
                bid_notice_id,
                scored.final_score,
            )
            try:
                async with self.session_factory() as session:
                    bid_notice_repo = BidNoticeRepository(session)
                    chunk_repo = ChunkRepository(session)
                    analysis_repo = AnalysisResultRepository(session)

                    bid_notice = await bid_notice_repo.get(bid_notice_id)
                    if bid_notice is None:
                        return SkippedNotice(
                            bid_notice_id=bid_notice_id, reason="입찰공고를 찾을 수 없습니다."
                        )

                    recommend_reason = list(fit.recommend_reason) if fit else []
                    weaknesses = list(fit.weaknesses) if fit else []
                    if scored.note and not weaknesses:
                        weaknesses = [
                            FitReason(
                                chunk_id=None,
                                reason=f"[배점표 채점 불가] {scored.note}",
                                grounding="inferred",
                                cited_source="none",
                            )
                        ]

                    summary = await self._summarize_notice(bid_notice_id, chunk_repo)

                    await self._save_analysis(
                        analysis_repo,
                        session,
                        req.search_set_id,
                        bid_notice_id,
                        scored.soft_score,
                        recommend_reason,
                        weaknesses,
                        summary,
                    )

                return ThirdFilterNoticeRead(
                    bid_notice_id=bid_notice_id,
                    final_score=scored.final_score,
                    aggregate_score=scored.item.aggregate_score,
                    recommend_reason=recommend_reason,
                    weaknesses=weaknesses,
                    summary=summary,
                    title=bid_notice.title,
                    demand_org=bid_notice.demand_org,
                )
            except Exception:
                logger.exception("공고 요약/저장 실패: bid_notice_id=%s", bid_notice_id)
                return SkippedNotice(
                    bid_notice_id=bid_notice_id, reason="검증/요약 중 오류가 발생했습니다."
                )

    async def _summarize_notice(self, bid_notice_id: int, chunk_repo: ChunkRepository) -> str | None:
        chunks = await chunk_repo.list_by_bid_notice(bid_notice_id)
        body = "\n".join(c.content for c in chunks if c.content)[:_SUMMARY_INPUT_MAX_CHARS]
        if not body:
            return None
        result = await self.llm.complete_structured(
            system=_SUMMARY_SYSTEM_PROMPT,
            user=body,
            response_model=NoticeSummaryResult,
        )
        return result.summary[:_SUMMARY_MAX_CHARS]

    @staticmethod
    async def _save_analysis(
        analysis_repo: AnalysisResultRepository,
        session,
        search_set_id: int,
        bid_notice_id: int,
        soft_score: int,
        recommend_reason: list[FitReason],
        weaknesses: list[FitReason],
        summary: str | None,
    ) -> None:
        analysis = await analysis_repo.get_by_search_set_and_notice(search_set_id, bid_notice_id)
        if analysis is None:
            # 1단계에서 배점표 미발견 등으로 evaluate 가 저장하지 못한 공고
            analysis = AnalysisResult(
                search_set_id=search_set_id,
                bid_notice_id=bid_notice_id,
                soft_score=soft_score,
            )
            await analysis_repo.add(analysis)
        analysis.recommend_reason = [r.model_dump() for r in recommend_reason]
        analysis.weaknesses = [r.model_dump() for r in weaknesses]
        analysis.summary = summary
        await session.commit()
