"""3차 필터 오케스트레이션.

흐름:
1. 입력된 모든 공고를 EvaluationService.evaluate 로 배점표 채점 (공고 간 병렬, 공고별 독립 세션)
2. final_score(= soft_score) 내림차순 정렬 → 상위 TOP_N 선별
   (aggregate_score 는 2차 필터가 이미 반영한 매칭도라 최종점수 산정에는 쓰지 않고 참고 정보로만 응답에 포함한다)
3. 상위 공고만 (a) ranked_chunks ↔ 회사 프로필/프로젝트 적합·부적합 LLM 검증(few-shot, 인용 강제)
   (b) 공고 내용 100자 요약 을 수행하고 AnalysisResult(recommend_reason/weaknesses/summary)에 저장
4. 상위 공고 목록 + 처리 제외(skipped) 목록 반환

동시성: SQLAlchemy AsyncSession 은 동시 쿼리를 허용하지 않으므로,
공고 간 병렬화는 공고마다 session_factory 로 새 세션을 열어 처리한다.
"""

from __future__ import annotations

import asyncio
import logging

from sqlmodel.ext.asyncio.session import AsyncSession

from app.common.exceptions import AppException
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
    ChunkFitJudgment,
    FitJudgmentResult,
    FitReason,
    NoticeResultIn,
    NoticeSummaryResult,
    SkippedNotice,
    ThirdFilterNoticeRead,
    ThirdFilterRequest,
    ThirdFilterResponse,
)
from app.services.evaluation_service import EvaluationService

logger = logging.getLogger(__name__)

_FIT_JUDGMENT_SYSTEM_PROMPT = (
    "너는 입찰공고 RFP 청크와 회사의 프로필/과거 프로젝트가 실제로 적합하게 매칭되었는지 "
    "검증하는 심사관이다.\n"
    "각 [검증 대상]마다 verdict='fit'(적합) 또는 'unfit'(부적합)을 판정하라.\n"
    "규칙:\n"
    "1. fit 판정 시 반드시 근거가 된 cited_source('profile'/'project'), cited_id, cited_field 를 "
    "인용하라. 인용할 근거가 없으면 무조건 unfit 이며 cited_source='none' 이다.\n"
    "2. 근거 없이 fit 을 지어내지 마라. 도메인·기술이 표면적으로만 겹치면 unfit 이다.\n"
    "3. reason 은 한국어 1~2문장으로 쓴다.\n"
    "4. 입력된 모든 chunk_id 에 대해 하나씩 판정을 반환하라.\n\n"
    "예시 1 (fit):\n"
    "[검증 대상] chunk_id=101 청크: '학사행정시스템 고도화. Java/Spring 기반 웹 개발 경험 필수'\n"
    "[매칭 근거] project#7: title='OO대학교 학사시스템 구축', tech_stack='Java, Spring Boot', "
    "performance='3년 무장애 운영'\n"
    "→ verdict='fit', cited_source='project', cited_id=7, cited_field='tech_stack', "
    "reason='요구 기술(Java/Spring)과 동일 도메인(학사시스템) 수행 실적이 project#7의 "
    "tech_stack·performance 로 확인됨.'\n\n"
    "예시 2 (unfit):\n"
    "[검증 대상] chunk_id=202 청크: '국방 보안관제 시스템. CC인증 및 보안관제 전문업체 지정 필수'\n"
    "[매칭 근거] profile#3: target_techs='웹 서비스, 모바일 앱', offered_solutions='쇼핑몰 솔루션'\n"
    "→ verdict='unfit', cited_source='none', cited_id=null, cited_field=null, "
    "reason='보안관제 자격요건을 뒷받침하는 항목이 프로필에 없음. 웹/모바일 경험은 무관.'"
)

_SUMMARY_SYSTEM_PROMPT = (
    "너는 공공입찰 공고 요약 어시스턴트다. 주어진 RFP 본문을 100자 이내 한국어 한 문장으로 "
    "요약하라. 사업명·발주기관·핵심 과업만 담아라."
)

_SUMMARY_INPUT_MAX_CHARS = 6000
_SUMMARY_MAX_CHARS = 100


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

    # ------------------------------------------------------------------ #
    # 전체 오케스트레이션
    # ------------------------------------------------------------------ #

    async def run(self, req: ThirdFilterRequest) -> ThirdFilterResponse:
        skipped: list[SkippedNotice] = []

        # 3차 필터 시작 → 검색세트 상태를 진행중으로 갱신(폴링용).
        await self._set_search_set_status(
            req.search_set_id, SearchSetStatus.ONGOING_THIRD_FILTER
        )

        # 1단계: 모든 공고 배점표 채점 (공고별 독립 세션으로 병렬)
        outcomes = await asyncio.gather(
            *[self._evaluate_notice(req, item) for item in req.results]
        )
        scored: list[_ScoredNotice] = []
        for outcome in outcomes:
            if isinstance(outcome, SkippedNotice):
                skipped.append(outcome)
            else:
                scored.append(outcome)

        # 2단계: 최종점수(=soft_score) 내림차순 상위 TOP_N
        scored.sort(key=lambda s: s.final_score, reverse=True)
        top = scored[: self.TOP_N]

        # 3단계: 상위 공고만 적합/부적합 검증 + 요약 + AnalysisResult 저장
        verified = await asyncio.gather(*[self._verify_and_summarize(req, s) for s in top])
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

    # ------------------------------------------------------------------ #
    # 1단계: 공고 1건 채점
    # ------------------------------------------------------------------ #

    async def _evaluate_notice(
        self, req: ThirdFilterRequest, item: NoticeResultIn
    ) -> _ScoredNotice | SkippedNotice:
        async with self._semaphore:
            try:
                async with self.session_factory() as session:
                    service = self.evaluation_service_factory(session, self.llm)
                    analysis = await service.evaluate(
                        search_set_id=req.search_set_id,
                        bid_notice_id=item.bid_notice_id,
                        company_id=req.company_id,
                    )
                return _ScoredNotice(item, soft_score=analysis.soft_score or 0)
            except AppException as e:
                # 배점표 미발견(404) 등은 부적격이 아니라 '배점표 가점 없음'으로 취급해
                # soft_score=0(=final_score 최하위)으로 랭킹에는 남긴다(skipped 로 빠뜨리지 않음).
                return _ScoredNotice(item, soft_score=0, note=e.message)
            except Exception:
                logger.exception("공고 채점 실패: bid_notice_id=%s", item.bid_notice_id)
                return SkippedNotice(
                    bid_notice_id=item.bid_notice_id, reason="채점 중 오류가 발생했습니다."
                )

    # ------------------------------------------------------------------ #
    # 3단계: 상위 TOP_N(5) 공고 검증 + 요약 + 저장
    #   run() 에서 상위 5건에 대해 각각 호출된다(아래 메서드는 공고 1건 단위 처리).
    #   상위 5건 모두 recommend_reason/weaknesses/summary 를 채워 AnalysisResult 에 저장한다.
    # ------------------------------------------------------------------ #

    async def _verify_and_summarize(
        self, req: ThirdFilterRequest, scored: _ScoredNotice
    ) -> ThirdFilterNoticeRead | SkippedNotice:
        bid_notice_id = scored.item.bid_notice_id
        async with self._semaphore:
            try:
                async with self.session_factory() as session:
                    bid_notice_repo = BidNoticeRepository(session)
                    chunk_repo = ChunkRepository(session)
                    profile_repo = CompanyProfileRepository(session)
                    project_repo = CompanyProjectRepository(session)
                    analysis_repo = AnalysisResultRepository(session)

                    bid_notice = await bid_notice_repo.get(bid_notice_id)
                    if bid_notice is None:
                        return SkippedNotice(
                            bid_notice_id=bid_notice_id, reason="입찰공고를 찾을 수 없습니다."
                        )

                    judgments = await self._judge_chunk_fits(
                        req, scored.item, chunk_repo, profile_repo, project_repo
                    )
                    recommend_reason, weaknesses = self._format_reasons(judgments)
                    if scored.note and not weaknesses:
                        weaknesses = [
                            FitReason(
                                chunk_id=None,
                                reason=f"[배점표 채점 불가] {scored.note}",
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
                logger.exception("공고 검증/요약 실패: bid_notice_id=%s", bid_notice_id)
                return SkippedNotice(
                    bid_notice_id=bid_notice_id, reason="검증/요약 중 오류가 발생했습니다."
                )

    async def _judge_chunk_fits(
        self,
        req: ThirdFilterRequest,
        item: NoticeResultIn,
        chunk_repo: ChunkRepository,
        profile_repo: CompanyProfileRepository,
        project_repo: CompanyProjectRepository,
    ) -> list[ChunkFitJudgment]:
        """ranked_chunks 각각의 청크 원문 ↔ 매칭 근거(프로필/프로젝트)를 LLM 1회 호출로 일괄 판정."""
        targets: list[str] = []
        for rc in item.ranked_chunks:
            chunk = await chunk_repo.get(rc.chunk_id)
            if chunk is None or not chunk.content:
                continue

            if rc.matched_source == "profile":
                profile = await profile_repo.get_by_company_id(req.company_id)
                evidence = (
                    f"profile#{profile.id}: company_scale={profile.company_scale}, "
                    f"target_techs={profile.target_techs}, offered_solutions={profile.offered_solutions}, "
                    f"strengths_diff={profile.strengths_diff}, credit_rating={profile.credit_rating}, "
                    f"sp_grade={profile.sp_grade}"
                    if profile
                    else "(등록된 프로필 없음)"
                )
            else:
                project = await project_repo.get(rc.matched_id)
                evidence = (
                    f"project#{project.id}: title={project.title}, domain={project.domain}, "
                    f"tech_stack={project.tech_stack}, develop_features={project.develop_features}, "
                    f"content={project.content}, performance={project.performance}"
                    if project
                    else f"(project#{rc.matched_id} 를 찾을 수 없음)"
                )

            targets.append(
                f"[검증 대상] chunk_id={rc.chunk_id} (rank={rc.rank}, score={rc.score})\n"
                f"청크: {chunk.content}\n"
                f"[매칭 근거] {evidence}"
            )

        if not targets:
            return []

        result = await self.llm.complete_structured(
            system=_FIT_JUDGMENT_SYSTEM_PROMPT,
            user="\n\n".join(targets),
            response_model=FitJudgmentResult,
        )

        # 방어적 가드: 인용 근거 없이 fit 이라 답하면 unfit 으로 강제 보정
        return [
            j.model_copy(update={"verdict": "unfit"})
            if j.verdict == "fit" and j.cited_source == "none"
            else j
            for j in result.judgments
        ]

    @staticmethod
    def _format_reasons(judgments: list[ChunkFitJudgment]) -> tuple[list[FitReason], list[FitReason]]:
        def to_reason(j: ChunkFitJudgment) -> FitReason:
            return FitReason(
                chunk_id=j.chunk_id,
                reason=j.reason,
                cited_source=j.cited_source,
                cited_id=j.cited_id,
                cited_field=j.cited_field,
            )

        fits = [to_reason(j) for j in judgments if j.verdict == "fit"]
        unfits = [to_reason(j) for j in judgments if j.verdict == "unfit"]
        return (fits, unfits)

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
