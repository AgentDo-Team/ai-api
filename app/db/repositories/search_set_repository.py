"""검색세트(search_set) 영속성 계층.

AnalysisResult 의 FK 를 충족시키기 위한 최소 구현이다. HardFilter 를 포함한
검색세트 전체 CRUD 는 별도 기능 범위라 여기서는 다루지 않는다.
"""

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
        """회사의 검색 세션(채팅방)을 최신순으로 반환한다. 채팅 목록용."""
        result = await self.session.exec(
            select(SearchSet)
            .where(SearchSet.company_id == company_id)
            .order_by(SearchSet.id.desc())
            .offset(offset)
            .limit(limit)
        )
        return list(result.all())

    async def delete(self, search_set: SearchSet) -> None:
        """chat_messages 등 하위 리소스는 FK ON DELETE CASCADE 로 함께 삭제된다."""
        await self.session.delete(search_set)

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

    async def set_progress(
        self, search_set_id: int, current: int, total: int
    ) -> SearchSet | None:
        """3차 필터 진행률(채점 끝난 공고 수/대상 수)을 갱신하고 커밋한다. 없으면 None.

        current 는 뒤로 가지 않는다. 공고를 동시에 채점하는 탓에 완료 순서와 커밋 순서가
        어긋나 낮은 값이 나중에 도착할 수 있어서다(진행률이 거꾸로 가 보이는 것을 막는다).
        """
        search_set = await self.get(search_set_id)
        if search_set is None:
            return None
        if current == 0:  # 시작 시 초기화는 예외적으로 되돌린다
            search_set.progress_current = 0
        else:
            search_set.progress_current = max(search_set.progress_current or 0, current)
        search_set.progress_total = total
        self.session.add(search_set)
        await self.session.commit()
        return search_set
