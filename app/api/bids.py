from fastapi import APIRouter, BackgroundTasks, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from app.db.session import get_session 
from app.schemas.response import ApiResponse
from app.services.bid_service import BidService

router = APIRouter(prefix="/bids", tags=["bids"])

@router.post("/sync", summary="입찰 공고 수집 및 파싱 트리거")
async def trigger_bid_sync(
    background_tasks: BackgroundTasks,
    session: AsyncSession = Depends(get_session) 
) -> ApiResponse[dict]:
    service = BidService(session)

    background_tasks.add_task(service.run_bid_pipeline)
    
    return ApiResponse.ok(
        data={"status": "processing"}, 
        message="공고 수집 및 파싱 파이프라인이 백그라운드에서 시작되었습니다."
    )