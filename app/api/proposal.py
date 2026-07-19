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
    analysis_result_id: int,
    company_id:int,
    session: AsyncSession = Depends(get_session)
):
    """
    제안서 초안 생성 파이프라인을 실행합니다.
    (분석 정보 조회 -> LLM JSON 생성 -> DOCX 파일 저장 -> DB 저장)
    """
    service = ProposalService(session)

    try:
        # 서비스의 통합 파이프라인 호출
        result = await service.process_proposal_generation(analysis_result_id, company_id)
        
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
    
@router.get("/download/{proposal_id}", summary="제안서 초안 DOCX 다운로드")
async def download_proposal(
    proposal_id: int,
    session: AsyncSession = Depends(get_session)
):
    """
    생성된 제안서 초안 DOCX 파일을 다운로드합니다.
    """
    service = ProposalService(session)

    try:
        # 1. 서비스에서 파일 경로와 파일명 가져오기
        file_path, file_name = await service.get_proposal_file_path(proposal_id)
        
        # 2. 한글 파일명 깨짐 방지를 위한 URL 인코딩 (핵심!)
        encoded_filename = urllib.parse.quote(file_name)

        # 3. FileResponse로 파일 반환
        return FileResponse(
            path=file_path,
            media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document", # DOCX MIME 타입
            filename=file_name,
            headers={
                # 브라우저가 다운로드 창을 띄우도록 유도하고, 한글 파일명을 인식하게 함
                "Content-Disposition": f"attachment; filename*=UTF-8''{encoded_filename}"
            }
        )

    except ValueError as e:
        # DB에 데이터가 없는 경우
        raise HTTPException(status_code=404, detail=str(e))
    except FileNotFoundError as e:
        # DB엔 있는데 실제 파일이 날아간 경우
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        # 기타 에러
        raise HTTPException(status_code=500, detail=f"파일 다운로드 중 오류 발생: {str(e)}")
    
@router.get("/list", summary="제안서 초안 목록 조회")
async def get_proposal_list(
    company_id: Optional[int] = Query(None, description="회사 ID로 필터링 (대시보드용)"),
    search_set_id: Optional[int] = Query(None, description="검색 세션 ID로 필터링 (특정 채팅방용)"),
    bid_notice_id: Optional[int] = Query(None, description="공고 ID로 필터링 (특정 공고용)"),
    session: AsyncSession = Depends(get_session)
):
    """
    생성된 제안서 초안 문서 목록을 조회합니다.
    (파라미터를 조합하여 원하는 조건의 목록만 가져올 수 있습니다.)
    """
    service = ProposalService(session)
    
    try:
        results = await service.get_proposals(
            company_id=company_id,
            search_set_id=search_set_id,
            bid_notice_id=bid_notice_id
        )
        
        return ApiResponse.ok(
            data=results,
            message="제안서 목록을 성공적으로 조회했습니다."
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"목록 조회 중 오류 발생: {str(e)}")