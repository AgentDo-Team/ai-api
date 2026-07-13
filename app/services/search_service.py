"""공고 검색 서비스.

현재는 1차 하드 필터링(정형 조건 → bid_notices WHERE)까지만 담당한다.
소프트 필터링(유사도 검색)·지연 임베딩은 이후 단계에서 이 서비스에 덧붙인다.
"""

from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.db.models.bid import BidNotice
from app.schemas.search import (
    BidSearchRequest,
    BidSearchResponse,
    BidSearchResultItem,
    HardFilterCondition,
)


def build_hard_filter_query(filters: HardFilterCondition):
    """정형 필터 조건을 bid_notices SELECT 쿼리로 조립한다.

    조건이 없는(None/빈 목록) 필드는 WHERE 절에 넣지 않아 '전체'로 취급한다.
    """
    query = select(BidNotice)

    # 도메인 분류코드: 채팅창 드롭다운이 넘긴 코드들과 매칭 (하나라도 일치)
    if filters.domain_codes:
        query = query.where(BidNotice.procurement_clsfc_no.in_(filters.domain_codes))

    # 공동수급: 방식명이 채워져 있으면 공동수급 가능 공고로 본다
    if filters.joint_venture is True:
        query = query.where(BidNotice.joint_venture_method.is_not(None))
    elif filters.joint_venture is False:
        query = query.where(BidNotice.joint_venture_method.is_(None))

    # 예산(원): 한쪽만 있으면 부등호 하나만 건다. budget_krw가 NULL인 공고는 제외된다.
    if filters.budget_min_krw is not None:
        query = query.where(BidNotice.budget_krw >= filters.budget_min_krw)
    if filters.budget_max_krw is not None:
        query = query.where(BidNotice.budget_krw <= filters.budget_max_krw)

    # 마감일 상한: 이 일시 이전에 마감되는 공고만
    if filters.deadline is not None:
        query = query.where(BidNotice.bid_deadline <= filters.deadline)

    return query


async def hard_filter_notices(
    session: AsyncSession, filters: HardFilterCondition
) -> list[BidNotice]:
    """1차 하드 필터링: 정형 조건에 맞는 공고 목록을 반환한다."""
    query = build_hard_filter_query(filters)
    result = await session.exec(query)
    return list(result.all())


async def search_bid_notices(
    session: AsyncSession, request: BidSearchRequest
) -> BidSearchResponse:
    """공고 검색 (현재는 하드 필터링 1차까지).

    request.message / company_id는 소프트 필터링(이후 단계)에서 사용한다.
    """
    notices = await hard_filter_notices(session, request.filters)
    items = [
        BidSearchResultItem(
            bid_notice_id=notice.id,
            notice_no=notice.notice_no,
            title=notice.title,
            demand_org=notice.demand_org,
            budget_krw=notice.budget_krw,
            bid_deadline=notice.bid_deadline,
        )
        for notice in notices
    ]
    return BidSearchResponse(hard_filtered_count=len(items), items=items)
