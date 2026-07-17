"""공고 검색 API 라우터.

JWT 인증 필수. 검색 주체 회사는 요청 본문이 아니라 토큰의 계정(=회사)에서 가져온다
(본인 프로필/프로젝트 기준으로만 검색하도록 강제).
"""

from fastapi import APIRouter, Depends
from sqlmodel.ext.asyncio.session import AsyncSession

from app.api.deps import CurrentAccountDep
from app.db.session import get_session
from app.schemas.response import ApiResponse
from app.schemas.search import BidSearchRequest, BidSearchResponse
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
