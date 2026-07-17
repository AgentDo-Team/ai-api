from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from app.db.session import get_session
from app.schemas.proposal import DraftRequest 
from app.schemas.response import ApiResponse
from app.services.proposal_service import ProposalService


router = APIRouter(prefix="/proposal", tags=["proposal"])

@router.post("/generate", summary="제안서 초안 생성")
async def generate_proposal(
    analysis_result_id: int,
    session: AsyncSession = Depends(get_session)
):
    """
    제안서 초안 생성 파이프라인을 실행합니다.

    1. 공고/검색 정보 조회
    2. LLM을 이용한 제안서 초안 생성
    3. File System MCP를 이용한 파일 저장
    4. 결과 DB 저장
    """

    service = ProposalService(session)

    result = await service.generate_proposal(analysis_result_id=analysis_result_id)

    return ApiResponse.ok(
        data=result,
        message="제안서 초안 생성이 완료되었습니다."
    )