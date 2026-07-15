"""평가기준표 참조 코퍼스(EvalCriteriaReference) 지연 적재.

app/rag/reference_data/eval_criteria_templates/*.md 를 읽어 임베딩한 뒤
eval_criteria_references 테이블에 적재한다. source_file 이 이미 있으면 건너뛴다
(재실행해도 중복 적재되지 않음).
"""

from __future__ import annotations

from pathlib import Path

# 모든 모델을 import 하여 SQLModel.metadata 에 테이블을 등록한다.
import app.db.models  # noqa: F401
from app.db.models.reference import EvalCriteriaReference
from app.db.repositories.eval_criteria_reference_repository import EvalCriteriaReferenceRepository
from app.llm.base import LLMProvider
from sqlmodel.ext.asyncio.session import AsyncSession

TEMPLATES_DIR = Path(__file__).resolve().parent.parent / "rag" / "reference_data" / "eval_criteria_templates"


async def _seed_missing_from_templates(session: AsyncSession, llm: LLMProvider) -> tuple[int, int]:
    """TEMPLATES_DIR의 md 파일들을 스캔해, 아직 적재되지 않은(source_file 기준) 문서만 임베딩·적재한다."""
    repo = EvalCriteriaReferenceRepository(session)

    added, skipped = 0, 0
    for path in sorted(TEMPLATES_DIR.glob("*.md")):
        if await repo.get_by_source_file(path.name) is not None:
            skipped += 1
            continue

        content = path.read_text(encoding="utf-8")
        embedding = await llm.embed(content)
        await repo.add(
            EvalCriteriaReference(source_file=path.name, content=content, embedding=embedding)
        )
        added += 1

    return added, skipped


async def ensure_seeded(session: AsyncSession, llm: LLMProvider) -> list[EvalCriteriaReference]:
    """참조 코퍼스(EvalCriteriaReference)를 조회할 때 호출하는 지연 시딩 진입점.

    임베딩된 참조가 하나도 없으면(최초 실행, seed CLI를 미리 돌리지 않은 환경 등)
    TEMPLATES_DIR의 md 파일들을 스캔해 즉시 임베딩·적재한 뒤 반환한다.
    커밋은 호출자(요청/트랜잭션을 소유한 쪽)의 책임이다.
    """
    repo = EvalCriteriaReferenceRepository(session)
    references = await repo.list_embedded()
    if references:
        return references

    await _seed_missing_from_templates(session, llm)
    return await repo.list_embedded()
