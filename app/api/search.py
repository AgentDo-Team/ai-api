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
from app.schemas.search import BidSearchRequest, BidSearchResponse
from app.services import search_service

router = APIRouter(prefix="/bid-notices", tags=["bid-notices"])

# 상태 스트림 튜닝 값. 서버가 이 주기로 DB 상태를 다시 읽어 변경분만 push 한다.
# (테스트에서 monkeypatch 로 0 에 가깝게 낮춰 즉시 돌린다.)
STATUS_POLL_INTERVAL_SECONDS = 2.0
# 3차 필터가 끝나지 않고 멈춰도 스트림이 영원히 열려 있지 않도록 하는 상한.
STATUS_STREAM_MAX_SECONDS = 600.0


@router.post("/search")
async def search_bid_notices(
    request: BidSearchRequest,
    current_account: CurrentAccountDep,
    session: AsyncSession = Depends(get_session),
) -> ApiResponse[BidSearchResponse]:
    """채팅창 공고 검색: 1차 하드 필터링 + 2차 소프트필터(청크 랭킹). 본인 회사 기준.

    company_id는 요청 본문이 아니라 JWT 토큰의 로그인 계정(=회사)에서 가져온다.
    """
    result = await search_service.search_bid_notices(
        session, current_account.id, request
    )
    return ApiResponse.ok(data=result)


def _sse(event: dict) -> str:
    """dict 이벤트를 SSE 한 줄(`data: {json}\\n\\n`)로 직렬화한다."""
    return f"data: {json.dumps(event, ensure_ascii=False)}\n\n"


async def _read_status(search_set_id: int) -> SearchSet | None:
    """상태 스트림 루프용: 매 폴링마다 새 세션으로 최신 커밋 상태를 읽는다.

    3차 필터는 별도 요청에서 status/progress 를 커밋한다. 하나의 세션(=하나의 트랜잭션)을
    스트림 내내 열어두면 그 커밋들이 보이지 않으므로, 읽을 때마다 짧은 세션을 새로 연다.
    """
    async with async_session_factory() as session:
        return await session.get(SearchSet, search_set_id)


async def _status_event_source(search_set_id: int) -> AsyncIterator[str]:
    """검색세트 상태가 바뀔 때마다 SSE status 이벤트를 흘리고, completed 에서 종료한다.

    이벤트(dict) 종류:
      - {"type": "status", "search_set_id", "status", "progress_current", "progress_total"}
      - {"type": "error", "message": <사유>}  — 세트 소멸/시간 초과 등
    """
    last_key = None
    deadline = time.monotonic() + STATUS_STREAM_MAX_SECONDS
    while True:
        search_set = await _read_status(search_set_id)
        if search_set is None:
            yield _sse({"type": "error", "message": "검색세트를 찾을 수 없습니다."})
            return

        # 상태 또는 진행률이 바뀐 경우에만 push (같은 값은 중복 전송하지 않는다).
        key = (search_set.status, search_set.progress_current, search_set.progress_total)
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
            yield _sse({"type": "error", "message": "상태 확인 시간이 초과되었습니다."})
            return
        await asyncio.sleep(STATUS_POLL_INTERVAL_SECONDS)


@router.get("/search-sets/{search_set_id}/status/stream")
async def stream_search_set_status(
    search_set_id: int,
    current_account: CurrentAccountDep,
    search_set_repo: Annotated[SearchSetRepository, Depends(get_search_set_repository)],
) -> StreamingResponse:
    """검색세트(채팅방) 분석 진행 상태를 SSE(text/event-stream)로 흘려보낸다.

    폴링을 대체한다. 상태가 바뀔 때마다 status 이벤트를 보내고,
    status=ongoing_third_filter 인 동안에는 progress_current/progress_total 도 함께 담는다.
    completed 에 도달하면 스트림을 닫는다. 소유권 검증은 첫 이벤트 이전에 수행하므로
    남의 세트/없는 세트면 403/404 로 바로 끝난다(스트림이 열리지 않는다).

    SSE 스트림이라 다른 엔드포인트와 달리 ApiResponse 로 감싸지 않는다.
    status: ongoing_second_filter → ongoing_third_filter → ongoing_report_generation
    → completed 순으로 바뀐다.
    status=ongoing_third_filter 인 동안에는 progress_current/progress_total 로
    "공고 몇 건까지 채점했는지"를 함께 내려준다. ongoing_report_generation 은 상위 공고
    선별이 끝나고 적합성 분석/요약 리포트를 작성 중인 단계다.
    """
    search_set = await search_set_repo.get(search_set_id)
    if search_set is None:
        raise AppException("검색세트를 찾을 수 없습니다.", status_code=404)
    if search_set.company_id != current_account.id:
        raise AppException("본인 회사의 검색세트만 조회할 수 있습니다.", status_code=403)

    return StreamingResponse(
        _status_event_source(search_set_id),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.get("/search-sets/{search_set_id}/analysis-results")
async def get_analysis_results(
    search_set_id: int,
    current_account: CurrentAccountDep,
    search_set_repo: Annotated[SearchSetRepository, Depends(get_search_set_repository)],
    analysis_repo: Annotated[
        AnalysisResultRepository, Depends(get_analysis_repository)
    ],
) -> ApiResponse[AnalysisResultsResponse]:
    """검색세트의 분석 결과(3차 필터 산출물) 목록 조회. 최종점수 내림차순. 본인 회사만."""
    search_set = await search_set_repo.get(search_set_id)
    if search_set is None:
        raise AppException("검색세트를 찾을 수 없습니다.", status_code=404)
    if search_set.company_id != current_account.id:
        raise AppException("본인 회사의 검색세트만 조회할 수 있습니다.", status_code=403)

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
        data=AnalysisResultsResponse(search_set_id=search_set_id, results=results)
    )
