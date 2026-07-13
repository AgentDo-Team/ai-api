"""공고 검색 API 라우터."""

from fastapi import APIRouter, Depends
from sqlmodel.ext.asyncio.session import AsyncSession

from app.db.session import get_session
from app.schemas.response import ApiResponse
from app.schemas.search import BidSearchRequest, BidSearchResponse
from app.services import search_service

router = APIRouter(prefix="/bid-notices", tags=["bid-notices"])


@router.post("/search")
async def search_bid_notices(
    request: BidSearchRequest,
    session: AsyncSession = Depends(get_session),
) -> ApiResponse[BidSearchResponse]:
    """채팅창 공고 검색 (현재 1차 하드 필터링까지)."""
    result = await search_service.search_bid_notices(session, request)
    return ApiResponse.ok(data=result)
