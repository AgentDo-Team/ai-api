"""EvaluationService 수동 실행용 스크립트 (일회성, 임시 파일).

실행 전: uv run python -m app.db.seed_dummy_data seed
         (출력된 bid_notice_id / company_id / search_set_id 를 아래 evaluate() 호출에 반영)

사용법:
  uv run python scratch_run_evaluation.py
"""

import asyncio
import json

from app.db.repositories.analysis_repository import AnalysisResultRepository
from app.db.repositories.bid_notice_repository import BidNoticeRepository
from app.db.repositories.chunk_repository import ChunkRepository
from app.db.repositories.company_repository import CompanyProfileRepository, CompanyProjectRepository
from app.db.repositories.eval_criteria_reference_repository import EvalCriteriaReferenceRepository
from app.db.repositories.search_set_repository import SearchSetRepository
from app.db.session import async_session_factory
from app.llm.openai_provider import OpenAIProvider
from app.services.evaluation_service import EvaluationService


async def main() -> None:
    async with async_session_factory() as session:
        service = EvaluationService(
            session=session,
            bid_notice_repo=BidNoticeRepository(session),
            chunk_repo=ChunkRepository(session),
            project_repo=CompanyProjectRepository(session),
            profile_repo=CompanyProfileRepository(session),
            analysis_repo=AnalysisResultRepository(session),
            search_set_repo=SearchSetRepository(session),
            eval_ref_repo=EvalCriteriaReferenceRepository(session),
            llm=OpenAIProvider(),
        )

        # seed_dummy_data.py 출력에서 확인한 실제 id로 바꿔주세요.
        result = await service.evaluate(search_set_id=2, bid_notice_id=3, company_id=5)

        print(f"soft_score: {result.soft_score}")
        print(json.dumps(result.chunk_judgments, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    asyncio.run(main())
