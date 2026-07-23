from fastapi import APIRouter, BackgroundTasks, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from app.db.session import get_session
from app.services.chunk_embedding_service import ChuckEmbeddingService
from app.services.ingestion_service import IngestionService
from app.schemas.response import ApiResponse

router = APIRouter(prefix="/ingest", tags=["ingestion"])

@router.post("/chunks", summary="대기 중인 공고 청킹 및 저장")
async def trigger_chunking(
    background_tasks: BackgroundTasks,
    session: AsyncSession = Depends(get_session)
):
    service = IngestionService(session)
    
    background_tasks.add_task(service.run_chunking_pipeline)
    
    return ApiResponse.ok(
        data={"status": "processing"},
        message="청크 분할 및 저장 작업이 백그라운드에서 시작되었습니다."
    )
@router.post("/embeddings", summary="생성된 청크의 벡터 임베딩 처리")
async def trigger_embedding(
    background_tasks: BackgroundTasks,
    session: AsyncSession = Depends(get_session)
):
    service = ChuckEmbeddingService(session)
    background_tasks.add_task(service.run_embedding_pipeline)
    
    return ApiResponse.ok(
        data={"status": "processing"},
        message="임베딩 생성 및 저장 작업이 백그라운드에서 시작되었습니다."
    )