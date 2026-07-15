"""공고 검색 서비스.

'전송' 한 번 = 새 검색 세션(채팅방) 시작. 흐름:
  1. SearchSet(채팅방) 생성
  2. 정형 필터 조건 저장 (HardFilter 1:1 + DomainCode 1:n)
  3. 사용자 메시지 저장 (ChatMessage, role='user') — 채팅방 이력 표시용
  4. 1차 하드 필터링(정형 조건 → bid_notices WHERE)으로 공고 목록 추출

소프트 필터링(유사도 검색)·지연 임베딩은 이후 단계에서 이 서비스에 덧붙인다.
"""

from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.db.models.analysis import ChatMessage
from app.db.models.bid import BidNotice
from app.db.models.search import DomainCode, HardFilter, SearchSet
from app.schemas.search import (
    BidSearchRequest,
    BidSearchResponse,
    BidSearchResultItem,
    HardFilterCondition,
)
from app.services import embedding_service
from app.services.second_filter_service import SecondFilterService

# 채팅방 제목 기본값 (자유형식 메시지가 없을 때)
_DEFAULT_SEARCH_TITLE = "공고 검색"


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


async def create_search_session(
    session: AsyncSession, request: BidSearchRequest
) -> SearchSet:
    """검색 세션(채팅방)을 생성하고 정형 필터·사용자 메시지를 저장한다.

    커밋까지 수행하며, id가 채워진 SearchSet을 돌려준다.
    """
    filters = request.filters

    # 1. 채팅방 생성 — 제목은 자유형식 메시지에서 따오고, 없으면 기본값
    title = request.message.strip() if request.message else ""
    search_set = SearchSet(
        company_id=request.company_id,
        title=(title[:200] or _DEFAULT_SEARCH_TITLE),
    )
    session.add(search_set)
    await session.flush()  # search_set.id 확보 (하위 FK에 필요)

    # 2. 정형 필터 저장 (검색세트:하드필터 = 1:1)
    hard_filter = HardFilter(
        search_set_id=search_set.id,
        joint_venture=filters.joint_venture,
        budget_min_krw=filters.budget_min_krw,
        budget_max_krw=filters.budget_max_krw,
        deadline=filters.deadline,
    )
    session.add(hard_filter)
    await session.flush()  # hard_filter.id 확보 (도메인코드 FK에 필요)

    # 3. 도메인 코드 저장 (하드필터:도메인코드 = 1:n). 요청엔 코드만 있어 이름은 비워둔다.
    for code in filters.domain_codes:
        session.add(DomainCode(hard_filter_id=hard_filter.id, domain_code=code))

    # 4. 사용자 메시지 저장 (자유형식). 없으면 저장하지 않는다.
    if request.message:
        session.add(
            ChatMessage(
                search_set_id=search_set.id, role="user", content=request.message
            )
        )

    await session.commit()
    return search_set


async def search_bid_notices(
    session: AsyncSession, request: BidSearchRequest
) -> BidSearchResponse:
    """공고 검색: 검색 세션 저장 + 1차 하드 필터링 + 2차 소프트필터(청크 랭킹).

    흐름: 전송 → 검색세션/필터 저장 → 지연 임베딩 → 1차 하드필터
          → 2차 소프트필터(개요·요구사항 청크를 자사 프로필/프로젝트와 유사도 비교)
    2차 결과(공고별 랭킹 청크)는 응답 second_filter 에 담기며 다음 단계(3차)로 넘어간다.
    """
    search_set = await create_search_session(session, request)

    # 지연 임베딩: 아직 임베딩 안 된 자사 프로필/프로젝트를 이 시점에 채운다.
    await embedding_service.ensure_company_embedded(session, request.company_id)

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

    # 2차 소프트필터: 하드필터 통과 공고를 개요·요구사항 청크 유사도로 랭킹한다.
    second = SecondFilterService(session)
    soft_result = await second.run(
        search_set_id=search_set.id,
        company_id=request.company_id,
        bid_notice_ids=[notice.id for notice in notices],
        query_text=request.message,
    )

    # 공고별 매칭도(aggregate_score)를 soft_score 로 채우고 내림차순 정렬한다.
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
