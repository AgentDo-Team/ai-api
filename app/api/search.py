"""공고 검색 API 라우터.

JWT 인증 필수. 검색 주체 회사는 요청 본문이 아니라 토큰의 계정(=회사)에서 가져온다
(본인 프로필/프로젝트 기준으로만 검색하도록 강제).
"""

import asyncio
import json
import time
from collections.abc import AsyncIterator
from typing import Annotated

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
from sqlmodel.ext.asyncio.session import AsyncSession

from app.api.deps import (
    CurrentAccountDep,
    get_analysis_repository,
    get_search_set_repository,
)
from app.common.exceptions import AppException
from app.core.enums import SearchSetStatus
from app.db.models.search import SearchSet
from app.db.repositories.analysis_repository import AnalysisResultRepository
from app.db.repositories.search_set_repository import SearchSetRepository
from app.db.session import async_session_factory, get_session
from app.schemas.analysis import AnalysisResultRead, AnalysisResultsResponse
from app.schemas.response import ApiResponse
from app.schemas.search import (
    BidSearchRequest,
    BidSearchResponse,
    SearchSetStatusResponse,
)
from app.services import search_service

router = APIRouter(prefix="/bid-notices", tags=["bid-notices"])

# 서버가 이 주기로 DB 상태를 다시 읽어 변경분만 push한다.
STATUS_POLL_INTERVAL_SECONDS = 2.0

# 스트림이 영원히 열려 있지 않도록 하는 최대 유지 시간.
STATUS_STREAM_MAX_SECONDS = 600.0


@router.post("/search")
async def search_bid_notices(
    request: BidSearchRequest,
    current_account: CurrentAccountDep,
    session: AsyncSession = Depends(get_session),
) -> ApiResponse[BidSearchResponse]:
    """채팅창 공고 검색.

    1차 하드 필터링과 2차 소프트필터를 로그인한 회사 기준으로 수행한다.
    company_id는 요청 본문이 아니라 JWT 토큰의 로그인 계정에서 가져온다.
    """
    result = await search_service.search_bid_notices(
        session,
        current_account.id,
        request,
    )
    return ApiResponse.ok(data=result)


def _sse(event: dict) -> str:
    """dict 이벤트를 SSE data 블록으로 직렬화한다."""
    return f"data: {json.dumps(event, ensure_ascii=False)}\n\n"


async def _read_status(search_set_id: int) -> SearchSet | None:
    """매 폴링마다 새 세션으로 최신 검색세트 상태를 읽는다.

    스트림에서 하나의 세션을 계속 사용하면 다른 요청에서 커밋한 상태 변경이
    보이지 않을 수 있으므로, 매번 새로운 세션을 사용한다.
    """
    async with async_session_factory() as session:
        return await session.get(SearchSet, search_set_id)


async def _status_event_source(search_set_id: int) -> AsyncIterator[str]:
    """검색세트 상태나 진행률이 변경될 때 SSE 이벤트를 전송한다."""
    last_key = None
    deadline = time.monotonic() + STATUS_STREAM_MAX_SECONDS

    while True:
        search_set = await _read_status(search_set_id)

        if search_set is None:
            yield _sse(
                {
                    "type": "error",
                    "message": "검색세트를 찾을 수 없습니다.",
                }
            )
            return

        key = (
            search_set.status,
            search_set.progress_current,
            search_set.progress_total,
        )

        if key != last_key:
            last_key = key

            yield _sse(
                {
                    "type": "status",
                    "search_set_id": search_set.id,
                    "status": search_set.status,
                    "progress_current": search_set.progress_current,
                    "progress_total": search_set.progress_total,
                }
            )

        if search_set.status == SearchSetStatus.COMPLETED.value:
            return

        if time.monotonic() >= deadline:
            yield _sse(
                {
                    "type": "error",
                    "message": "상태 확인 시간이 초과되었습니다.",
                }
            )
            return

        await asyncio.sleep(STATUS_POLL_INTERVAL_SECONDS)


@router.get("/search-sets/{search_set_id}/status")
async def get_search_set_status(
    search_set_id: int,
    current_account: CurrentAccountDep,
    search_set_repo: Annotated[
        SearchSetRepository,
        Depends(get_search_set_repository),
    ],
) -> ApiResponse[SearchSetStatusResponse]:
    """검색세트 분석 진행 상태를 일반 JSON 응답으로 조회한다."""
    search_set = await search_set_repo.get(search_set_id)

    if search_set is None:
        raise AppException(
            "검색세트를 찾을 수 없습니다.",
            status_code=404,
        )

    if search_set.company_id != current_account.id:
        raise AppException(
            "본인 회사의 검색세트만 조회할 수 있습니다.",
            status_code=403,
        )

    return ApiResponse.ok(
        data=SearchSetStatusResponse(
            search_set_id=search_set.id,
            status=search_set.status,
            failure_reason=search_set.failure_reason,
        )
    )


@router.get("/search-sets/{search_set_id}/status/stream")
async def stream_search_set_status(
    search_set_id: int,
    current_account: CurrentAccountDep,
    search_set_repo: Annotated[
        SearchSetRepository,
        Depends(get_search_set_repository),
    ],
) -> StreamingResponse:
    """검색세트 분석 진행 상태를 SSE로 전송한다.

    소유권 검증은 스트림을 열기 전에 수행한다. 상태 또는 진행률이 변경될 때마다
    이벤트를 전송하고 completed 상태에 도달하면 스트림을 종료한다.
    """
    search_set = await search_set_repo.get(search_set_id)

    if search_set is None:
        raise AppException(
            "검색세트를 찾을 수 없습니다.",
            status_code=404,
        )

    if search_set.company_id != current_account.id:
        raise AppException(
            "본인 회사의 검색세트만 조회할 수 있습니다.",
            status_code=403,
        )

    return StreamingResponse(
        _status_event_source(search_set_id),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )


@router.get("/search-sets/{search_set_id}/analysis-results")
async def get_analysis_results(
    search_set_id: int,
    current_account: CurrentAccountDep,
    search_set_repo: Annotated[
        SearchSetRepository,
        Depends(get_search_set_repository),
    ],
    analysis_repo: Annotated[
        AnalysisResultRepository,
        Depends(get_analysis_repository),
    ],
) -> ApiResponse[AnalysisResultsResponse]:
    """검색세트의 분석 결과를 최종점수 내림차순으로 조회한다."""
    search_set = await search_set_repo.get(search_set_id)

    if search_set is None:
        raise AppException(
            "검색세트를 찾을 수 없습니다.",
            status_code=404,
        )

    if search_set.company_id != current_account.id:
        raise AppException(
            "본인 회사의 검색세트만 조회할 수 있습니다.",
            status_code=403,
        )

    rows = await analysis_repo.list_by_search_set(search_set_id)

    results = [
        AnalysisResultRead(
            bid_notice_id=analysis.bid_notice_id,
            final_score=analysis.soft_score,
            recommend_reason=analysis.recommend_reason or [],
            weaknesses=analysis.weaknesses or [],
            summary=analysis.summary,
            title=notice.title,
            demand_org=notice.demand_org,
        )
        for analysis, notice in rows
    ]

    return ApiResponse.ok(
        data=AnalysisResultsResponse(
            search_set_id=search_set_id,
            results=results,
        )
    )