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

STATUS_POLL_INTERVAL_SECONDS = 2.0

STATUS_STREAM_MAX_SECONDS = 600.0


@router.post("/search")
async def search_bid_notices(
    request: BidSearchRequest,
    current_account: CurrentAccountDep,
    session: AsyncSession = Depends(get_session),
) -> ApiResponse[BidSearchResponse]:
    result = await search_service.search_bid_notices(
        session,
        current_account.id,
        request,
    )
    return ApiResponse.ok(data=result)


def _sse(event: dict) -> str:
    return f"data: {json.dumps(event, ensure_ascii=False)}\n\n"


async def _read_status(search_set_id: int) -> SearchSet | None:
    async with async_session_factory() as session:
        return await session.get(SearchSet, search_set_id)


async def _status_event_source(search_set_id: int) -> AsyncIterator[str]:
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