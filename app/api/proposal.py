from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from app.db.session import get_session
from app.schemas.proposal import DraftRequest 
from app.schemas.response import ApiResponse
from app.services.proposal_service import ProposalService
from fastapi import APIRouter, Depends, HTTPException


router = APIRouter(prefix="/proposal", tags=["proposal"])

@router.post("/generate", summary="제안서 초안 생성 전체 파이프라인")
async def generate_proposal(
    analysis_result_id: int,
    session: AsyncSession = Depends(get_session)
):
    """
    제안서 초안 생성 파이프라인을 실행합니다.
    (분석 정보 조회 -> LLM JSON 생성 -> DOCX 파일 저장 -> DB 저장)
    """
    service = ProposalService(session)

    try:
        # 서비스의 통합 파이프라인 호출
        result = await service.process_proposal_generation(analysis_result_id)
        
        # 성공 응답
        return ApiResponse.ok(
            data=result,
            message="제안서 초안 파이프라인이 성공적으로 완료되었습니다."
        )
        
    except ValueError as e:
        # 데이터를 찾을 수 없는 경우 (404)
        raise HTTPException(status_code=404, detail=str(e))
    except RuntimeError as e:
        # LLM 생성 실패 등 (500)
        raise HTTPException(status_code=500, detail=str(e))
    except Exception as e:
        # 기타 예기치 않은 에러
        raise HTTPException(status_code=500, detail=f"파이프라인 실행 중 오류 발생: {str(e)}")