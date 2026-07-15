"""평가기준표 참조 예시(EvalCriteriaReference) 영속성 계층.

bid_notice에 종속되지 않는 전역 참조 코퍼스다. 하드 필터가 실패했을 때 세컨드 티어
(semantic fallback, app/rag/retrievers/hybrid_search.py) 쿼리 임베딩으로 쓰인다.
"""

from __future__ import annotations

from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.db.models.reference import EvalCriteriaReference


class EvalCriteriaReferenceRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def add(self, reference: EvalCriteriaReference) -> EvalCriteriaReference:
        self.session.add(reference)
        await self.session.flush()
        return reference

    async def bulk_add(self, references: list[EvalCriteriaReference]) -> list[EvalCriteriaReference]:
        for reference in references:
            self.session.add(reference)
        await self.session.flush()
        return references

    async def get_by_source_file(self, source_file: str) -> EvalCriteriaReference | None:
        result = await self.session.exec(
            select(EvalCriteriaReference).where(EvalCriteriaReference.source_file == source_file)
        )
        return result.first()

    async def list_embedded(self) -> list[EvalCriteriaReference]:
        result = await self.session.exec(
            select(EvalCriteriaReference).where(EvalCriteriaReference.embedding.is_not(None))
        )
        return list(result.all())

    async def delete_all(self) -> None:
        references = (await self.session.exec(select(EvalCriteriaReference))).all()
        for reference in references:
            await self.session.delete(reference)
