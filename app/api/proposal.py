from typing import Optional

from fastapi import APIRouter, Depends, Query
from fastapi.responses import FileResponse
from sqlalchemy.ext.asyncio import AsyncSession
import urllib
from app.db.session import get_session
from app.schemas.proposal import DraftRequest 
from app.schemas.response import ApiResponse
from app.services.proposal_service import ProposalService
from fastapi import APIRouter, Depends, HTTPException


router = APIRouter(prefix="/proposal", tags=["proposal"])

@router.post("/generate", summary="제안서 초안 생성 전체 파이프라인")
async def generate_proposal(
    bid_notice_id: int,
    company_id:int,
    session: AsyncSession = Depends(get_session)
):
    service = ProposalService(session)

    try:
        result = await service.process_proposal_generation(bid_notice_id, company_id)
        
    
        return ApiResponse.ok(
            data=result,
            message="제안서 초안 파이프라인이 성공적으로 완료되었습니다."
        )
        
    except ValueError as e:

        raise HTTPException(status_code=404, detail=str(e))
    except RuntimeError as e:

        raise HTTPException(status_code=500, detail=str(e))
    except Exception as e:

        raise HTTPException(status_code=500, detail=f"파이프라인 실행 중 오류 발생: {str(e)}")
    
@router.get("/download/{proposal_id}", summary="제안서 초안 DOCX 다운로드")
async def download_proposal(
    proposal_id: int,
    session: AsyncSession = Depends(get_session)
):
    service = ProposalService(session)

    try:
        file_path, file_name = await service.get_proposal_file_path(proposal_id)
        encoded_filename = urllib.parse.quote(file_name)
        return FileResponse(
            path=file_path,
            media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document", 
            filename=file_name,
            headers={
                "Content-Disposition": f"attachment; filename*=UTF-8''{encoded_filename}"
            }
        )

    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"파일 다운로드 중 오류 발생: {str(e)}")
    
@router.get("/list", summary="제안서 초안 목록 조회")
async def get_proposal_list(
    company_id:int,
    session: AsyncSession = Depends(get_session)
):
    service = ProposalService(session)
    
    try:
        results = await service.get_proposals(
            company_id=company_id,
        )
        
        return ApiResponse.ok(
            data=results,
            message="제안서 목록을 성공적으로 조회했습니다."
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"목록 조회 중 오류 발생: {str(e)}")