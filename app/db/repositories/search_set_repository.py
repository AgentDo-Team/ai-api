"""검색세트(search_set) 영속성 계층.

AnalysisResult 의 FK 를 충족시키기 위한 최소 구현이다. HardFilter 를 포함한
검색세트 전체 CRUD 는 별도 기능 범위라 여기서는 다루지 않는다.
"""

from __future__ import annotations

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

    async def set_status(
        self, search_set_id: int, status: SearchSetStatus
    ) -> SearchSet | None:
        """검색세트 상태를 갱신하고 커밋한다. 존재하지 않으면 None."""
        search_set = await self.get(search_set_id)
        if search_set is None:
            return None
        search_set.status = status.value
        self.session.add(search_set)
        await self.session.commit()
        return search_set
