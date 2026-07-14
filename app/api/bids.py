from fastapi import APIRouter, BackgroundTasks, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from app.db.session import get_session 
from app.schemas.response import ApiResponse
from app.services.bid_service import BidService, run_bid_pipeline

router = APIRouter(prefix="/bids", tags=["bids"])

@router.post("/sync", summary="입찰 공고 수집 및 파싱 트리거")
async def trigger_bid_sync(
    background_tasks: BackgroundTasks,
    session: AsyncSession = Depends(get_session) # 세션 의존성 주입
) -> ApiResponse[dict]:
    """
    나라장터 API를 조회하여 최신 공고를 수집하고, 
    제안요청서를 다운로드 및 파싱하여 DB에 저장합니다.
    (시간이 오래 걸리므로 백그라운드에서 실행됩니다.)
    """
    
    # 1. 서비스 인스턴스 생성 (주입받은 세션 사용)
    service = BidService(session)
    
    # 2. background_tasks.add_task에 '함수'가 아닌 '인스턴스.메서드'를 인자와 함께 전달
    background_tasks.add_task(service.run_bid_pipeline)
    
    return ApiResponse.ok(
        data={"status": "processing"}, 
        message="공고 수집 및 파싱 파이프라인이 백그라운드에서 시작되었습니다."
    )