from fastapi import APIRouter, BackgroundTasks, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from app.db.session import get_session # 세션 의존성 주입을 위한 의존성 함수
from app.services.ingestion_service import IngestionService
from app.schemas.response import ApiResponse

router = APIRouter(prefix="/ingest", tags=["ingestion"])

@router.post("/chunks", summary="대기 중인 공고 청킹 및 저장")
async def trigger_chunking(
    background_tasks: BackgroundTasks,
    session: AsyncSession = Depends(get_session)
):
    """
    RDB에 저장된 PENDING 상태의 공고를 가져와 청크 분할 후 Vector DB에 저장합니다.
    작업 시간이 길기 때문에 백그라운드에서 처리됩니다.
    """
    service = IngestionService(session)
    
    # 백그라운드 작업으로 등록
    background_tasks.add_task(service.run_chunking_pipeline)
    
    return ApiResponse.ok(
        data={"status": "processing"},
        message="청크 분할 및 저장 작업이 백그라운드에서 시작되었습니다."
    )