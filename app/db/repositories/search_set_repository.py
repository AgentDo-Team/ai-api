from __future__ import annotations

from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.core.enums import SearchSetStatus
from app.db.models.search import SearchSet


class SearchSetRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def add(self, search_set: SearchSet) -> SearchSet:
        self.session.add(search_set)
        await self.session.flush()
        return search_set

    async def get(self, search_set_id: int) -> SearchSet | None:
        return await self.session.get(SearchSet, search_set_id)

    async def list_by_company(
        self, company_id: int, limit: int = 50, offset: int = 0
    ) -> list[SearchSet]:
        result = await self.session.exec(
            select(SearchSet)
            .where(SearchSet.company_id == company_id)
            .order_by(SearchSet.id.desc())
            .offset(offset)
            .limit(limit)
        )
        return list(result.all())

    async def delete(self, search_set: SearchSet) -> None:
        await self.session.delete(search_set)

    async def set_status(
        self, search_set_id: int, status: SearchSetStatus
    ) -> SearchSet | None:
        search_set = await self.get(search_set_id)
        if search_set is None:
            return None
        search_set.status = status.value
        self.session.add(search_set)
        await self.session.commit()
        return search_set

    async def set_progress(
        self, search_set_id: int, current: int, total: int
    ) -> SearchSet | None:
        search_set = await self.get(search_set_id)
        if search_set is None:
            return None
        if current == 0:  
            search_set.progress_current = 0
        else:
            search_set.progress_current = max(search_set.progress_current or 0, current)
        search_set.progress_total = total
        self.session.add(search_set)
        await self.session.commit()
        return search_set
