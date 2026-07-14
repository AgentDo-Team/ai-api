"""평가기준표 기반 입찰공고 채점 파이프라인.

1~2단계: extract_evaluation_criteria (table_filter 규칙 기반 스캔 + LLM 세부항목 분리)
3~5단계: _judge_criterion_once (하이브리드 검색 + LLM 강제 인용 채점 + 무근거시 최하점 가드)
6단계:   score_criterion (K=3 반복 후 평균/다수결)
전체:    evaluate (문서 전체 오케스트레이션, AnalysisResult 영속화)
"""

from __future__ import annotations

import asyncio

from app.common.exceptions import AppException
from app.db.models.analysis import AnalysisResult
from app.db.repositories.analysis_repository import AnalysisResultRepository
from app.db.repositories.bid_notice_repository import BidNoticeRepository
from app.db.repositories.chunk_repository import ChunkRepository
from app.db.repositories.company_repository import CompanyProfileRepository, CompanyProjectRepository
from app.db.repositories.eval_criteria_reference_repository import EvalCriteriaReferenceRepository
from app.db.repositories.search_set_repository import SearchSetRepository
from app.llm.base import LLMProvider
from app.rag.chunking.table_filter import is_eval_criteria_table
from app.rag.retrievers.hybrid_search import hybrid_search_chunks, semantic_fallback_search_chunks
from app.schemas.evaluation import (
    CriteriaExtractionResult,
    CriterionJudgment,
    CriterionScoreResult,
    EvalCriterion,
)

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


class EvaluationService:
    EVAL_K = 3

    def __init__(
        self,
        session,
        bid_notice_repo: BidNoticeRepository,
        chunk_repo: ChunkRepository,
        project_repo: CompanyProjectRepository,
        profile_repo: CompanyProfileRepository,
        analysis_repo: AnalysisResultRepository,
        search_set_repo: SearchSetRepository,
        eval_ref_repo: EvalCriteriaReferenceRepository,
        llm: LLMProvider,
    ) -> None:
        self.session = session
        self.bid_notice_repo = bid_notice_repo
        self.chunk_repo = chunk_repo
        self.project_repo = project_repo
        self.profile_repo = profile_repo
        self.analysis_repo = analysis_repo
        self.search_set_repo = search_set_repo
        self.eval_ref_repo = eval_ref_repo
        self.llm = llm

    # ------------------------------------------------------------------ #
    # 1~2단계: 평가기준표 탐지 + 세부항목 분리, 입찰공고서에서 평가기준표 보고 list[항목명,설명,만점] 가져옴
    # ------------------------------------------------------------------ #

    async def extract_evaluation_criteria(self, bid_notice_id: int) -> list[EvalCriterion]:
        chunks = await self.chunk_repo.list_by_bid_notice(bid_notice_id)
        # 1차: 청크에서 '평가기준표'에 해당하는 청크만 규칙 기반으로 추려낸다 (하드 필터)
        matched = [c for c in chunks if c.content and is_eval_criteria_table(c.content)]

        # 2차: 하드 필터가 하나도 못 찾으면, 참조 코퍼스(EvalCriteriaReference)를 쿼리로 삼아
        # 이 bid_notice 청크들 중 '평가기준표'와 의미적으로 유사한 청크를 하이브리드(semantic) 검색으로 찾는다.
        if not matched:
            fallback_results = await semantic_fallback_search_chunks(
                self.chunk_repo, self.eval_ref_repo, self.llm, bid_notice_id, limit=5
            )
            matched = [r.chunk for r in fallback_results if r.chunk.content]

        if not matched:
            raise AppException("평가기준표를 찾을 수 없습니다.", status_code=404)

        joined_text = "\n\n".join(c.content for c in matched if c.content)
        result = await self.llm.complete_structured(
            system=_CRITERIA_EXTRACTION_SYSTEM_PROMPT,
            user=joined_text,
            response_model=CriteriaExtractionResult,
        )
        if not result.criteria:
            raise AppException("평가기준표에서 세부평가 항목을 분리하지 못했습니다.", status_code=422)
        return result.criteria # criteria: list[EvalCriterion]

    # ------------------------------------------------------------------ #
    # 3~5단계: 세부항목 1개, 1회 채점
    # ------------------------------------------------------------------ #

    async def _judge_criterion_once( self, bid_notice_id: int, company_id: int, criterion: EvalCriterion) -> CriterionJudgment:
        # EvalCriterion [항목명,설명,만점]
        query_text = criterion.name + (f" {criterion.description}" if criterion.description else "")
        # 평가 항목과 관련된 청크를 추가로 집어넣고 배점표의 항목이 구체적으로 어떤건지 보완
        # 하이브리드 서치를 통해 상위 5개 청크 가져온다
        search_results = await hybrid_search_chunks(
            self.chunk_repo, self.llm, bid_notice_id, query_text, limit=5
        )
        # 평가항목
        projects = await self.project_repo.list_by_company(company_id, limit=50, offset=0)
        profile = await self.profile_repo.get_by_company_id(company_id)

        user_prompt = self._build_judgment_prompt(criterion, search_results, projects, profile)
        judgment = await self.llm.complete_structured(
            system=_JUDGMENT_SYSTEM_PROMPT,
            user=user_prompt,
            response_model=CriterionJudgment,
        )

        # 방어적 가드: 근거 없다면서 점수를 매기거나, 배점을 초과하는 응답은 코드에서 강제 보정한다.
        if judgment.verdict == "no_evidence" and judgment.score != 0:
            judgment = judgment.model_copy(update={"score": 0})
        judgment = judgment.model_copy(
            update={"score": max(0.0, min(judgment.score, criterion.max_score))}
        )
        return judgment

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
    # ------------------------------------------------------------------ #

    async def score_criterion(
        self, bid_notice_id: int, company_id: int, criterion: EvalCriterion
    ) -> CriterionScoreResult:
        runs: list[CriterionJudgment] = await asyncio.gather(
            *[
                self._judge_criterion_once(bid_notice_id, company_id, criterion)
                for _ in range(self.EVAL_K)
            ]
        )

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

        results = [
            await self.score_criterion(bid_notice_id, company_id, criterion)
            for criterion in criteria
        ]

        soft_score = round(sum(r.earned_score for r in results))
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

        analysis_result = AnalysisResult(
            search_set_id=search_set_id,
            bid_notice_id=bid_notice_id,
            soft_score=soft_score,
            chunk_judgments=chunk_judgments,
        )
        await self.analysis_repo.add(analysis_result)
        await self.session.commit()
        return analysis_result
