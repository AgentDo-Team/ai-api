import logging

from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.common.exceptions import AppException
from app.core.enums import ProcurementCategory, SearchSetStatus
from app.db.models.analysis import ChatMessage
from app.db.models.bid import BidNotice
from app.db.models.search import HardFilter, SearchSet
from app.schemas.search import (
    BidSearchRequest,
    BidSearchResponse,
    BidSearchResultItem,
    HardFilterCondition,
)
from app.services import embedding_service
from app.services.second_filter_service import (
    DEFAULT_CANDIDATE_K,
    DEFAULT_FINAL_K,
    SecondFilterService,
)

logger = logging.getLogger(__name__)
_DEFAULT_SEARCH_TITLE = "공고 검색"


def _resolve_domain_name(procurement_clsfc_no: str | None) -> str | None:
    if procurement_clsfc_no is None:
        return None
    member = ProcurementCategory.__members__.get(procurement_clsfc_no)
    return member.value if member else None


def build_hard_filter_query(filters: HardFilterCondition):
    query = select(BidNotice)

    if filters.domain_code is not None:
        query = query.where(BidNotice.procurement_clsfc_no == filters.domain_code)

    if filters.joint_venture is True:
        query = query.where(BidNotice.joint_venture_method.is_not(None))
    elif filters.joint_venture is False:
        query = query.where(BidNotice.joint_venture_method.is_(None))
    if filters.budget_min_krw is not None:
        query = query.where(BidNotice.budget_krw >= filters.budget_min_krw)
    if filters.budget_max_krw is not None:
        query = query.where(BidNotice.budget_krw <= filters.budget_max_krw)

    if filters.deadline is not None:
        query = query.where(BidNotice.bid_deadline <= filters.deadline)

    return query


async def hard_filter_notices(
    session: AsyncSession, filters: HardFilterCondition
) -> list[BidNotice]:
    query = build_hard_filter_query(filters)
    result = await session.exec(query)
    return list(result.all())


async def create_search_session(
    session: AsyncSession, company_id: int, request: BidSearchRequest
) -> SearchSet:
    filters = request.filters

    title = request.message.strip() if request.message else ""
    search_set = SearchSet(
        company_id=company_id,
        title=(title[:200] or _DEFAULT_SEARCH_TITLE),
    )
    session.add(search_set)
    await session.flush()  
    hard_filter = HardFilter(
        search_set_id=search_set.id,
        domain_code=filters.domain_code,
        joint_venture=filters.joint_venture,
        budget_min_krw=filters.budget_min_krw,
        budget_max_krw=filters.budget_max_krw,
        deadline=filters.deadline,
    )
    session.add(hard_filter)
    await session.flush()

    if request.message:
        session.add(
            ChatMessage(
                search_set_id=search_set.id, role="user", content=request.message
            )
        )

    await session.commit()
    return search_set


def _to_result_items(notices: list[BidNotice]) -> list[BidSearchResultItem]:
    """공고 목록을 응답 아이템으로 변환한다(soft_score 는 2차에서 채운다)."""
    return [
        BidSearchResultItem(
            bid_notice_id=notice.id,
            notice_no=notice.notice_no,
            title=notice.title,
            demand_org=notice.demand_org,
            budget_krw=notice.budget_krw,
            bid_deadline=notice.bid_deadline,
            domain_name=_resolve_domain_name(notice.procurement_clsfc_no),
        )
        for notice in notices
    ]


async def search_bid_notices(
    session: AsyncSession, company_id: int, request: BidSearchRequest
) -> BidSearchResponse:
    search_set = await create_search_session(session, company_id, request)

    try:
        search_set.status = SearchSetStatus.ONGOING_SECOND_FILTER.value
        search_set.failure_reason = None
        session.add(search_set)
        await session.commit()
        await embedding_service.ensure_company_embedded(session, company_id)

        notices = await hard_filter_notices(session, request.filters)
        items = _to_result_items(notices)

        second = SecondFilterService(session)
        soft_result = await second.run(
            search_set_id=search_set.id,
            company_id=company_id,
            bid_notice_ids=[notice.id for notice in notices],
            query_text=request.message,
            candidate_k=DEFAULT_CANDIDATE_K,  
            final_k=DEFAULT_FINAL_K,  
        )

    except Exception as exc:
        
        await session.rollback()
        persisted = await session.get(SearchSet, search_set.id)
        if persisted is not None:
            persisted.status = SearchSetStatus.FAILED.value
            persisted.failure_reason = (
                exc.message
                if isinstance(exc, AppException)
                else "2차 소프트필터 처리 중 오류가 발생했습니다."
            )
            session.add(persisted)
            await session.commit()
        if isinstance(exc, AppException):
            logger.warning(
                "2차 소프트필터 중단: search_set_id=%s, reason=%s",
                search_set.id,
                exc.message,
            )
        else:
            logger.exception("2차 소프트필터 실패: search_set_id=%s", search_set.id)
        raise

    score_by_notice = {r.bid_notice_id: r.aggregate_score for r in soft_result.results}
    for item in items:
        item.soft_score = score_by_notice.get(item.bid_notice_id)
    items.sort(key=lambda item: (item.soft_score or 0.0), reverse=True)

    return BidSearchResponse(
        search_set_id=search_set.id,
        hard_filtered_count=len(items),
        items=items,
        second_filter=soft_result,
    )
