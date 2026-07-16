"""공고 검색 API 라우터."""

from fastapi import APIRouter, Depends
from sqlmodel.ext.asyncio.session import AsyncSession

from app.api.auth import get_current_account
from app.db.models.company import Company
from app.db.session import get_session
from app.schemas.response import ApiResponse
from app.schemas.search import BidSearchRequest, BidSearchResponse
from app.services import search_service

router = APIRouter(prefix="/bid-notices", tags=["bid-notices"])


@router.post("/search")
async def search_bid_notices(
    request: BidSearchRequest,
    current_account: Company = Depends(get_current_account),
    session: AsyncSession = Depends(get_session),
) -> ApiResponse[BidSearchResponse]:
    """채팅창 공고 검색: 1차 하드 필터링 + 2차 소프트필터(청크 랭킹).

    company_id는 요청 본문이 아니라 JWT 토큰의 로그인 계정(=회사)에서 가져온다.
    """
    result = await search_service.search_bid_notices(
        session, current_account.id, request
    )
    return ApiResponse.ok(data=result)
