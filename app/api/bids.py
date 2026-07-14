from fastapi import APIRouter, BackgroundTasks
from app.schemas.response import ApiResponse
from app.services.bid_service import run_bid_pipeline

router = APIRouter(prefix="/bids", tags=["bids"])

@router.post("/sync", summary="입찰 공고 수집 및 파싱 트리거")
async def trigger_bid_sync(background_tasks: BackgroundTasks) -> ApiResponse[dict]:
    """
    나라장터 API를 조회하여 최신 공고를 수집하고, 
    제안요청서를 다운로드 및 파싱하여 DB에 저장합니다.
    (시간이 오래 걸리므로 백그라운드에서 실행됩니다.)
    """
    # 백그라운드 작업으로 등록 (API 응답은 즉시 반환하고 뒤에서 파싱이 돎)
    background_tasks.add_task(run_bid_pipeline)
    
    return ApiResponse.ok(
        data={"status": "processing"}, 
        message="공고 수집 및 파싱 파이프라인이 백그라운드에서 시작되었습니다."
    )