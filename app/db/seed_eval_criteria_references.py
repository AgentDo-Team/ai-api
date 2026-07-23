from __future__ import annotations

from pathlib import Path

import app.db.models  
from app.db.models.reference import EvalCriteriaReference
from app.db.repositories.eval_criteria_reference_repository import EvalCriteriaReferenceRepository
from app.llm.base import LLMProvider
from sqlmodel.ext.asyncio.session import AsyncSession

TEMPLATES_DIR = Path(__file__).resolve().parent.parent / "rag" / "reference_data" / "eval_criteria_templates"


async def _seed_missing_from_templates(session: AsyncSession, llm: LLMProvider) -> tuple[int, int]:
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
    repo = EvalCriteriaReferenceRepository(session)
    references = await repo.list_embedded()
    if references:
        return references

    await _seed_missing_from_templates(session, llm)
    return await repo.list_embedded()
