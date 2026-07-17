"""공고 검색 서비스.

'전송' 한 번 = 새 검색 세션(채팅방) 시작. 흐름:
  1. SearchSet(채팅방) 생성
  2. 정형 필터 조건 저장 (HardFilter 1:1). 도메인 분류코드는 정규화 테이블 없이
     ProcurementCategory 로 검증된 코드 문자열 하나(HardFilter.domain_code)로 저장한다.
  3. 사용자 메시지 저장 (ChatMessage, role='user') — 채팅방 이력 표시용
  4. 1차 하드 필터링(정형 조건 → bid_notices WHERE)으로 공고 목록 추출

소프트 필터링(유사도 검색)·지연 임베딩은 이후 단계에서 이 서비스에 덧붙인다.
"""

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

# 채팅방 제목 기본값 (자유형식 메시지가 없을 때)
_DEFAULT_SEARCH_TITLE = "공고 검색"


def _resolve_domain_name(procurement_clsfc_no: str | None) -> str | None:
    """공고의 분류코드를 ProcurementCategory 기준 한글명으로 변환한다.

    수집 파이프라인이 20개 화이트리스트 코드만 저장하므로(app/services/bid_service.py의
    SI_domain_codes) 정상적으로는 항상 매칭되지만, 등록 안 된 코드는 None으로 처리한다.
    """
    if procurement_clsfc_no is None:
        return None
    member = ProcurementCategory.__members__.get(procurement_clsfc_no)
    return member.value if member else None


def build_hard_filter_query(filters: HardFilterCondition):
    """정형 필터 조건을 bid_notices SELECT 쿼리로 조립한다.

    조건이 없는(None/빈 목록) 필드는 WHERE 절에 넣지 않아 '전체'로 취급한다.
    """
    query = select(BidNotice)

    # 도메인 분류코드: 채팅창 드롭다운이 넘긴 코드 하나와 일치
    if filters.domain_code is not None:
        query = query.where(BidNotice.procurement_clsfc_no == filters.domain_code)

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
    session: AsyncSession, company_id: int, request: BidSearchRequest
) -> SearchSet:
    """검색 세션(채팅방)을 생성하고 정형 필터·사용자 메시지를 저장한다.

    company_id는 JWT 토큰에서 검증된 값(요청 본문이 아님)을 그대로 받는다.
    커밋까지 수행하며, id가 채워진 SearchSet을 돌려준다.
    """
    filters = request.filters

    # 1. 채팅방 생성 — 제목은 자유형식 메시지에서 따오고, 없으면 기본값
    title = request.message.strip() if request.message else ""
    search_set = SearchSet(
        company_id=company_id,
        title=(title[:200] or _DEFAULT_SEARCH_TITLE),
    )
    session.add(search_set)
    await session.flush()  # search_set.id 확보 (하위 FK에 필요)

    # 2. 정형 필터 저장 (검색세트:하드필터 = 1:1). 도메인 코드는 요청 시점에 이미
    # ProcurementCategory 로 검증된 값이라 그대로 저장한다.
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

    # 3. 사용자 메시지 저장 (자유형식). 없으면 저장하지 않는다.
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
    """공고 검색: 검색 세션 저장 + 1차 하드필터 + 2차 소프트필터(청크 랭킹).

    company_id는 JWT 토큰에서 검증된 값. 흐름: 전송 → 검색세션/필터 저장 → 지연 임베딩
    → 1차 하드필터 → 2차 소프트필터(개요·요구사항 청크를 자사 프로필/프로젝트와 유사도
    비교). 2차 결과는 응답 second_filter 에 담겨 3차로 넘어간다.
    """
    search_set = await create_search_session(session, company_id, request)

    try:
        # 검색 준비 및 2차 소프트필터 시작 상태를 먼저 기록한다.
        search_set.status = SearchSetStatus.ONGOING_SECOND_FILTER.value
        search_set.failure_reason = None
        session.add(search_set)
        await session.commit()

        # 지연 임베딩: 폼 준비 여부를 검증하고 미임베딩 입력만 한 번 채운다.
        await embedding_service.ensure_company_embedded(session, company_id)

        notices = await hard_filter_notices(session, request.filters)
        items = _to_result_items(notices)

        # 2차 소프트필터: 하드필터 통과 공고를 개요·요구사항 청크 유사도로 랭킹한다.
        second = SecondFilterService(session)
        soft_result = await second.run(
            search_set_id=search_set.id,
            company_id=company_id,
            bid_notice_ids=[notice.id for notice in notices],
            query_text=request.message,
            candidate_k=DEFAULT_CANDIDATE_K,  # 공고별 RRF 후보 수
            final_k=DEFAULT_FINAL_K,  # 공고당 3차로 내려줄 최종 랭킹 청크 수
        )

    except Exception as exc:
        # DB 오류로 트랜잭션이 실패한 경우에도 상태 기록이 가능하도록 먼저 되돌린다.
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
