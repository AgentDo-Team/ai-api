"""공고 검색 API 라우터.

JWT 인증 필수. 검색 주체 회사는 요청 본문이 아니라 토큰의 계정(=회사)에서 가져온다
(본인 프로필/프로젝트 기준으로만 검색하도록 강제).
"""

from typing import Annotated

from fastapi import APIRouter, Depends
from sqlmodel.ext.asyncio.session import AsyncSession

from app.api.deps import (
    CurrentAccountDep,
    get_analysis_repository,
    get_search_set_repository,
)
from app.common.exceptions import AppException
from app.db.repositories.analysis_repository import AnalysisResultRepository
from app.db.repositories.search_set_repository import SearchSetRepository
from app.db.session import get_session
from app.schemas.analysis import AnalysisResultRead, AnalysisResultsResponse
from app.schemas.response import ApiResponse
from app.schemas.search import BidSearchRequest, BidSearchResponse, SearchSetStatusResponse
from app.services import search_service

router = APIRouter(prefix="/bid-notices", tags=["bid-notices"])


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


@router.get("/search-sets/{search_set_id}/status")
async def get_search_set_status(
    search_set_id: int,
    current_account: CurrentAccountDep,
    search_set_repo: Annotated[SearchSetRepository, Depends(get_search_set_repository)],
) -> ApiResponse[SearchSetStatusResponse]:
    """검색세트(채팅방) 분석 진행 상태 조회. 2차/3차 필터 진행 여부를 프론트가 폴링한다.

    status: ongoing_second_filter → ongoing_third_filter → completed 순으로 바뀐다.
    """
    search_set = await search_set_repo.get(search_set_id)
    if search_set is None:
        raise AppException("검색세트를 찾을 수 없습니다.", status_code=404)
    if search_set.company_id != current_account.id:
        raise AppException("본인 회사의 검색세트만 조회할 수 있습니다.", status_code=403)

    return ApiResponse.ok(
        data=SearchSetStatusResponse(
            search_set_id=search_set.id,
            status=search_set.status,
            failure_reason=search_set.failure_reason,
        )
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
