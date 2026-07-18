"""평가기준표 기반 입찰공고 채점 파이프라인.

1~2단계: extract_evaluation_criteria (table_filter 규칙 기반 스캔 + LLM 세부항목 분리)
         규칙 기반으로 배점표 청크를 못 찾으면 표준 평가표 템플릿을 대체 채점표로 사용한다.
3~4단계: _build_criterion_prompt (하이브리드 검색으로 항목별 채점 프롬프트 구성, 항목 간 병렬)
5단계:   전체 항목(x EVAL_K 회차)의 프롬프트를 모아 LLMProvider.complete_structured_batch
         (랭체인 Runnable.abatch) 로 한 번에 배치 전송 → LLM 요청 수는 그대로지만 개별
         asyncio.gather 호출 대신 단일 배치 호출로 묶인다. 이후 _apply_guard 로 무근거시 최하점 보정.
6단계:   _aggregate_criterion (EVAL_K회 반복 후 평균/다수결, 기본 1회)
전체:    evaluate (문서 전체 오케스트레이션, AnalysisResult 영속화)

동시성: 항목별 프롬프트 구성(DB 조회)은 병렬로 돈다. AsyncSession 은 동시 쿼리를 허용하지
않으므로 항목마다 session_factory 로 독립 세션을 열어 DB 를 읽고, 배치 LLM 호출 전에 반납한다.
"""

from __future__ import annotations

import asyncio
import logging
from pathlib import Path

from app.common.exceptions import AppException
from app.db.models.analysis import AnalysisResult
from app.db.repositories.analysis_repository import AnalysisResultRepository
from app.db.repositories.bid_notice_repository import BidNoticeRepository
from app.db.repositories.chunk_repository import ChunkRepository
from app.db.repositories.company_repository import CompanyProfileRepository, CompanyProjectRepository
from app.db.repositories.eval_criteria_reference_repository import EvalCriteriaReferenceRepository
from app.db.repositories.search_set_repository import SearchSetRepository
from app.db.session import async_session_factory
from app.llm.base import LLMProvider
from app.rag.chunking.table_filter import is_eval_criteria_table
from app.rag.retrievers.hybrid_search import hybrid_search_chunks
from app.schemas.evaluation import (
    CriteriaExtractionResult,
    CriterionJudgment,
    CriterionScoreResult,
    EvalCriterion,
)

logger = logging.getLogger(__name__)

_CRITERIA_EXTRACTION_SYSTEM_PROMPT = (
    "너는 공공입찰 RFP의 평가기준표를 분석하는 어시스턴트다. "
    "주어진 평가기준표 원문을 세부평가 항목 단위로 분리해라. "
    "각 항목의 name(항목명), description(평가 기준 설명, 없으면 null), "
    "max_score(배점, 숫자)를 정확히 원문 그대로 추출한다. 원문에 없는 항목을 만들어내지 마라."
)

_JUDGMENT_SYSTEM_PROMPT = (
    "너는 회사가 특정 입찰 평가항목에서 몇 점을 받을 수 있을지 채점하는 어시스턴트다. "
    "아래에 (1) 평가항목과 관련된 RFP 청크들, (2) 회사 프로필, (3) 회사의 과거 프로젝트 목록이 주어진다. "
    "회사의 과거 프로젝트/프로필 중에서 이 평가항목을 뒷받침하는 명확한 근거를 찾아라. "
    "근거를 찾으면 verdict='found' 로 하고, 반드시 근거가 된 chunk_id, project_id, field(예: performance, "
    "develop_features, tech_stack, content, strengths_diff 등)를 정확히 인용해라. "
    "근거를 찾지 못하면 verdict='no_evidence' 로 하고 score=0 으로 답하라. "
    "절대로 근거 없이 점수를 지어내지 마라. score 는 0 이상 max_score 이하여야 한다."
)

# 규칙 기반 하드필터가 배점표 청크를 못 찾을 때 사용할 표준 평가표 템플릿.
# 임베딩(semantic) 검색이 불안정해, 하이브리드 검색 대신 이 템플릿을 대체 채점표로 쓴다.
_FALLBACK_TEMPLATE_DIR = (
    Path(__file__).resolve().parents[1] / "rag" / "reference_data" / "eval_criteria_templates"
)
_FALLBACK_TEMPLATE_FILENAME = "01_기본제안서_평가표.md"


class EvaluationService:
    EVAL_K = 1  # 항목당 반복 채점 횟수. 2 이상이면 평균/다수결 집계가 의미를 가진다.
    MAX_CONCURRENT_CRITERIA = 5  # 항목 병렬 채점 상한 (DB 커넥션/LLM rate limit 보호)

    def __init__(
        self,
        session,
        bid_notice_repo: BidNoticeRepository,
        chunk_repo: ChunkRepository,
        analysis_repo: AnalysisResultRepository,
        search_set_repo: SearchSetRepository,
        eval_ref_repo: EvalCriteriaReferenceRepository,
        llm: LLMProvider,
        session_factory=async_session_factory,
    ) -> None:
        self.session = session
        self.bid_notice_repo = bid_notice_repo
        self.chunk_repo = chunk_repo
        self.analysis_repo = analysis_repo
        self.search_set_repo = search_set_repo
        self.eval_ref_repo = eval_ref_repo
        self.llm = llm
        self.session_factory = session_factory

    # ------------------------------------------------------------------ #
    # 1~2단계: 평가기준표 탐지 + 세부항목 분리, 입찰공고서에서 평가기준표 보고 list[항목명,설명,만점] 가져옴
    # ------------------------------------------------------------------ #

    async def extract_evaluation_criteria(self, bid_notice_id: int) -> list[EvalCriterion]:
        chunks = await self.chunk_repo.list_by_bid_notice(bid_notice_id)
        # 1차: 청크에서 '평가기준표'에 해당하는 청크만 규칙 기반으로 추려낸다 (하드 필터)
        matched = [c for c in chunks if c.content and is_eval_criteria_table(c.content)]

        if matched:
            joined_text = "\n\n".join(c.content for c in matched if c.content)
        else:
            # 하드 필터가 배점표 청크를 하나도 못 찾은 경우.
            # 임베딩 하이브리드 검색은 결과가 불안정해, 표준 평가표 템플릿을 대체 채점표로 사용한다.
            print(
                f"[evaluation] bid_notice_id={bid_notice_id}: "
                f"적절한 배점표 청크를 찾지 못해 대체 채점표를 사용합니다 "
                f"(template={_FALLBACK_TEMPLATE_FILENAME})"
            )
            joined_text = self._load_fallback_template_text()

        result = await self.llm.complete_structured(
            system=_CRITERIA_EXTRACTION_SYSTEM_PROMPT,
            user=joined_text,
            response_model=CriteriaExtractionResult,
        )
        if not result.criteria:
            raise AppException("평가기준표에서 세부평가 항목을 분리하지 못했습니다.", status_code=422)
        return result.criteria # criteria: list[EvalCriterion]

    @staticmethod
    def _load_fallback_template_text() -> str:
        """대체 채점표(표준 평가표 템플릿) 원문을 읽어온다."""
        path = _FALLBACK_TEMPLATE_DIR / _FALLBACK_TEMPLATE_FILENAME
        return path.read_text(encoding="utf-8")

    # ------------------------------------------------------------------ #
    # 3~4단계: 세부항목 1개의 채점 프롬프트 구성 (LLM 호출 없음, DB 조회만)
    # ------------------------------------------------------------------ #

    async def _build_criterion_prompt(
        self, bid_notice_id: int, company_id: int, criterion: EvalCriterion
    ) -> str:
        # EvalCriterion [항목명,설명,만점]
        query_text = criterion.name + (f" {criterion.description}" if criterion.description else "")

        # 항목별 프롬프트 구성은 병렬로 돌므로 공유 세션 대신 항목별 독립 세션에서 DB 를 읽고,
        # 배치 LLM 호출 전에 세션을 닫아 커넥션을 풀에 반납한다.
        async with self.session_factory() as session:
            # 평가 항목과 관련된 청크를 추가로 집어넣고 배점표의 항목이 구체적으로 어떤건지 보완
            # 하이브리드 서치를 통해 상위 5개 청크 가져온다
            search_results = await hybrid_search_chunks(
                ChunkRepository(session), self.llm, bid_notice_id, query_text, limit=5
            )
            # 평가항목
            projects = await CompanyProjectRepository(session).list_by_company(
                company_id, limit=50, offset=0
            )
            profile = await CompanyProfileRepository(session).get_by_company_id(company_id)

        return self._build_judgment_prompt(criterion, search_results, projects, profile)

    @staticmethod
    def _apply_guard(judgment: CriterionJudgment, criterion: EvalCriterion) -> CriterionJudgment:
        """방어적 가드: 근거 없다면서 점수를 매기거나, 배점을 초과하는 응답은 코드에서 강제 보정한다."""
        if judgment.verdict == "no_evidence" and judgment.score != 0:
            judgment = judgment.model_copy(update={"score": 0})
        return judgment.model_copy(
            update={"score": max(0.0, min(judgment.score, criterion.max_score))}
        )

    @staticmethod
    def _build_judgment_prompt(criterion, search_results, projects, profile) -> str:
        chunk_lines = "\n".join(
            f"- chunk_id={r.chunk.id}: {r.chunk.content}" for r in search_results if r.chunk.content
        ) or "(관련 RFP 청크를 찾지 못함)"

        project_lines = "\n".join(
            f"- project_id={p.id} title={p.title} domain={p.domain} tech_stack={p.tech_stack} "
            f"develop_features={p.develop_features} content={p.content} performance={p.performance}"
            for p in projects
        ) or "(등록된 프로젝트 없음)"

        profile_line = (
            f"company_scale={profile.company_scale}, target_techs={profile.target_techs}, "
            f"offered_solutions={profile.offered_solutions}, strengths_diff={profile.strengths_diff}, "
            f"credit_rating={profile.credit_rating}, sp_grade={profile.sp_grade}"
            if profile
            else "(등록된 프로필 없음)"
        )

        return (
            f"[평가항목]\nname={criterion.name}\ndescription={criterion.description}\n"
            f"max_score={criterion.max_score}\n\n"
            f"[관련 RFP 청크]\n{chunk_lines}\n\n"
            f"[회사 프로필]\n{profile_line}\n\n"
            f"[회사 과거 프로젝트]\n{project_lines}"
        )

    # ------------------------------------------------------------------ #
    # 6단계: K회 반복 후 평균/다수결
    # 지금은 속도 때문에 해당 반복로직은 작동 안하게 해놨음 ㅠㅠ
    # ------------------------------------------------------------------ #

    @staticmethod
    def _aggregate_criterion(
        criterion: EvalCriterion, runs: list[CriterionJudgment]
    ) -> CriterionScoreResult:
        earned_score = sum(r.score for r in runs) / len(runs)
        found_count = sum(1 for r in runs if r.verdict == "found")
        verdict = "found" if found_count > len(runs) / 2 else "no_evidence"

        representative = next((r for r in runs if r.verdict == verdict), runs[0])

        return CriterionScoreResult(
            criterion=criterion,
            earned_score=earned_score,
            verdict=verdict,
            chunk_id=representative.chunk_id,
            project_id=representative.project_id,
            field=representative.field,
            reason=representative.reason,
            k_runs=runs,
        )

    # ------------------------------------------------------------------ #
    # 전체 오케스트레이션
    # ------------------------------------------------------------------ #

    async def evaluate(
        self, search_set_id: int, bid_notice_id: int, company_id: int
    ) -> AnalysisResult:
        if await self.search_set_repo.get(search_set_id) is None:
            raise AppException("검색세트를 찾을 수 없습니다.", status_code=404)
        if await self.bid_notice_repo.get(bid_notice_id) is None:
            raise AppException("입찰공고를 찾을 수 없습니다.", status_code=404)

        criteria = await self.extract_evaluation_criteria(bid_notice_id)
        total = len(criteria)

        # 항목별 프롬프트 구성(DB 조회)은 병렬로 돈다 (항목마다 독립 세션이라 동시 실행
        # 안전, 세마포어로 상한 제한). LLM 호출은 여기 없다.
        semaphore = asyncio.Semaphore(self.MAX_CONCURRENT_CRITERIA)

        async def _build(index: int, criterion: EvalCriterion) -> str:
            async with semaphore:
                logger.info(
                    "  [notice=%s] 항목 채점 프롬프트 구성 (%d/%d) %s",
                    bid_notice_id,
                    index,
                    total,
                    criterion.name,
                )
                return await self._build_criterion_prompt(bid_notice_id, company_id, criterion)

        prompts = await asyncio.gather(
            *[_build(i, criterion) for i, criterion in enumerate(criteria, start=1)]
        )

        # 항목(x EVAL_K 회차) 전체를 한 번의 랭체인 abatch 호출로 묶어 LLM 요청을 일괄 전송한다.
        requests = [
            (_JUDGMENT_SYSTEM_PROMPT, prompt) for prompt in prompts for _ in range(self.EVAL_K)
        ]
        logger.info(
            "  [notice=%s] 항목 %d개 x %d회 배치 채점 요청 전송 (%d건)",
            bid_notice_id,
            total,
            self.EVAL_K,
            len(requests),
        )
        raw_judgments = await self.llm.complete_structured_batch(
            requests=requests, response_model=CriterionJudgment
        )

        results: list[CriterionScoreResult] = [
            self._aggregate_criterion(
                criterion,
                [
                    self._apply_guard(j, criterion)
                    for j in raw_judgments[i * self.EVAL_K : (i + 1) * self.EVAL_K]
                ],
            )
            for i, criterion in enumerate(criteria)
        ]

        # 배점표 항목별 만점은 공고마다 원문 그대로 추출되어 제각각이므로(30점 고정이 아님),
        # 원점수 합계를 실제 만점 합계로 나눠 0~100 범위로 정규화한다.
        raw_score = sum(r.earned_score for r in results)
        max_possible = sum(r.criterion.max_score for r in results)
        soft_score = round(raw_score / max_possible * 100) if max_possible > 0 else 0
        chunk_judgments = [
            {
                "criterion": r.criterion.name,
                "max_score": r.criterion.max_score,
                "earned_score": r.earned_score,
                "verdict": r.verdict,
                "chunk_id": r.chunk_id,
                "project_id": r.project_id,
                "field": r.field,
                "reason": r.reason,
            }
            for r in results
        ]

        # 같은 (search_set_id, bid_notice_id) 재평가 시 uq_analysis_searchset_notice 위반을
        # 피하기 위해 upsert 한다. recommend_reason/weaknesses/summary 는 건드리지 않는다.
        analysis_result = await self.analysis_repo.get_by_search_set_and_notice(
            search_set_id, bid_notice_id
        )
        if analysis_result is not None:
            analysis_result.soft_score = soft_score
            analysis_result.chunk_judgments = chunk_judgments
        else:
            analysis_result = AnalysisResult(
                search_set_id=search_set_id,
                bid_notice_id=bid_notice_id,
                soft_score=soft_score,
                chunk_judgments=chunk_judgments,
            )
            await self.analysis_repo.add(analysis_result)
        await self.session.commit()
        return analysis_result
