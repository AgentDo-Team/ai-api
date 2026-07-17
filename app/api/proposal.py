from fastapi import APIRouter, HTTPException
from app.mcp.client import run_proposal_agent
from app.schemas.proposal import DraftRequest 
from app.schemas.response import ApiResponse


router = APIRouter(prefix="/proposal", tags=["proposal"])

@router.post("/generate", summary="제안서 초안 자동 생성 에이전트 호출")
async def generate_proposal_draft(
    req: DraftRequest
) -> ApiResponse[dict]:
    """
    사용자의 요청을 받아 순수 MCP 클라이언트(Ollama 에이전트)를 실행하고,
    제안서 초안 문서(DOCX)를 생성한 뒤 결과를 반환합니다.
    """
    try:
        # 1. 에이전트에게 내릴 명확한 지시(Prompt) 구성
        user_prompt = (
            f"검색셋 ID {req.search_set_id}번과 공고 ID {req.bid_notice_id}번을 사용해서 "
            f"제안서 초안을 만들고 최종 문서 경로를 알려줘."
        )
        
        # 2. MCP 클라이언트 에이전트 실행 (기존 client.py 역할)
        # 여기서 시간이 좀 걸리므로 비동기(await)로 대기합니다.
        agent_result = await run_proposal_agent(user_prompt)
        
        # 3. 정형화된 응답 반환
        return ApiResponse.ok(
            data={"agent_message": agent_result},
            message="AI 에이전트가 제안서 초안 작업을 성공적으로 완료했습니다."
        )
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"에이전트 실행 중 오류 발생: {str(e)}")