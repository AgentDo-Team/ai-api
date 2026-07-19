"""챗봇 채팅 세션 CRUD + 대화 엔드포인트.

세션(채팅방)은 기존 SearchSet 을 재사용하고, 메시지는 chat_messages 테이블에 쌓인다.
JWT 인증 필수. 경로의 company_id 가 토큰의 계정(=회사) id 와 다르면 403.
"""

import json
from typing import Annotated

from fastapi import APIRouter, Depends, Path
from fastapi.responses import StreamingResponse

from app.api.deps import (
    get_chat_service,
    get_collaboration_agent_service,
    verify_company_access,
)
from app.common.exceptions import AppException
from app.schemas.chat import (
    ChatMessageRead,
    ChatRequest,
    ChatSessionRead,
    WeaknessAgentRequest,
    WeaknessAgentResumeRequest,
)
from app.schemas.response import ApiResponse
from app.services.chat_service import ChatService
from app.services.collaboration_agent_service import CollaborationAgentService

router = APIRouter(
    prefix="/api/companies/{company_id}/chat-sessions",
    tags=["chat"],
    dependencies=[Depends(verify_company_access)],
)

ServiceDep = Annotated[ChatService, Depends(get_chat_service)]
AgentServiceDep = Annotated[
    CollaborationAgentService, Depends(get_collaboration_agent_service)
]
CompanyIdPath = Annotated[int, Path(description="회사 ID", ge=1)]
SessionIdPath = Annotated[int, Path(description="채팅 세션 ID", ge=1)]

AUTH_ERRORS = {
    401: {"description": "인증 정보가 없거나 유효하지 않음"},
    403: {"description": "본인 회사의 리소스가 아님"},
}
NOT_FOUND = {404: {"description": "채팅 세션을 찾을 수 없음"}, **AUTH_ERRORS}


@router.get(
    "",
    summary="채팅 세션 목록",
    description="회사의 채팅 세션(채팅방)을 최신순으로 조회한다.",
    responses=AUTH_ERRORS,
)
async def list_sessions(
    company_id: CompanyIdPath, service: ServiceDep
) -> ApiResponse[list[ChatSessionRead]]:
    sessions = await service.list_sessions(company_id)
    return ApiResponse.ok(data=[ChatSessionRead.of(s) for s in sessions])


@router.delete(
    "/{session_id}",
    summary="채팅 세션 삭제",
    description="채팅 세션과 그 대화 내역을 삭제한다.",
    responses=NOT_FOUND,
)
async def delete_session(
    company_id: CompanyIdPath, session_id: SessionIdPath, service: ServiceDep
) -> ApiResponse[None]:
    await service.delete_session(company_id, session_id)
    return ApiResponse.ok(message="채팅 세션이 삭제되었습니다.")


@router.get(
    "/{session_id}/messages",
    summary="채팅 세션 대화 내역",
    description="세션의 이전 대화(user/assistant)를 시간순으로 조회한다. 이전 세션 연결용.",
    responses=NOT_FOUND,
)
async def list_messages(
    company_id: CompanyIdPath, session_id: SessionIdPath, service: ServiceDep
) -> ApiResponse[list[ChatMessageRead]]:
    messages = await service.get_messages(company_id, session_id)
    return ApiResponse.ok(data=[ChatMessageRead.of(m) for m in messages])


@router.post(
    "/{session_id}/messages",
    summary="챗봇에게 질문",
    description="질문을 저장하고, RAG 로 답변을 생성해 저장한 뒤 챗봇 답변을 반환한다. "
    "bid_notice_id 를 주면 해당 공고 청크를 근거로 답한다.",
    responses=NOT_FOUND,
)
async def send_message(
    company_id: CompanyIdPath,
    session_id: SessionIdPath,
    body: ChatRequest,
    service: ServiceDep,
) -> ApiResponse[ChatMessageRead]:
    message = await service.chat(
        company_id, session_id, body.question, body.bid_notice_id
    )
    return ApiResponse.ok(data=ChatMessageRead.of(message))


def _sse(event: dict) -> str:
    """dict 이벤트를 SSE 한 줄(`data: {json}\\n\\n`)로 직렬화한다."""
    return f"data: {json.dumps(event, ensure_ascii=False)}\n\n"


@router.post(
    "/{session_id}/messages/stream",
    summary="챗봇에게 질문 (스트리밍)",
    description="send_message 와 동일하나, 답변 토큰을 생성되는 대로 SSE(text/event-stream)로 "
    "흘려보낸다. 이벤트: delta(부분 토큰) → done(저장된 message_id). 오류는 error 이벤트로 온다. "
    "SSE 스트림이라 다른 엔드포인트와 달리 ApiResponse 로 감싸지 않는다.",
    responses=NOT_FOUND,
)
async def send_message_stream(
    company_id: CompanyIdPath,
    session_id: SessionIdPath,
    body: ChatRequest,
    service: ServiceDep,
) -> StreamingResponse:
    async def event_source():
        try:
            async for event in service.chat_stream(
                company_id, session_id, body.question, body.bid_notice_id
            ):
                yield _sse(event)
        except AppException as exc:
            # 소유권 실패 등은 스트림 시작 직후 발생한다. HTTP 헤더는 이미 200 이라
            # 상태코드 대신 error 이벤트(payload)로 전달한다.
            yield _sse(
                {"type": "error", "message": exc.message, "status": exc.status_code}
            )
        except Exception:
            yield _sse({"type": "error", "message": "답변 생성에 실패했습니다."})

    return StreamingResponse(
        event_source(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


def _agent_stream_response(events) -> StreamingResponse:
    """약점 해결 에이전트 이벤트(AsyncIterator[dict])를 SSE 스트림으로 감싼다."""

    async def event_source():
        try:
            async for event in events:
                yield _sse(event)
        except AppException as exc:
            yield _sse(
                {"type": "error", "message": exc.message, "status": exc.status_code}
            )
        except Exception:
            yield _sse({"type": "error", "message": "에이전트 실행에 실패했습니다."})

    return StreamingResponse(
        event_source(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.post(
    "/{session_id}/weakness-agent/stream",
    summary="회사 약점 해결 에이전트 실행 (스트리밍)",
    description="약점 분석이 끝난 공고를 대상으로, 협력사로 약점을 해소할 수 있는지 판단해 "
    "협업 제안 메일(이메일 서브그래프) 또는 웹검색 추천 리포트(검색 서브그래프)로 분기한다. "
    "그래프의 각 노드 진행 상태를 SSE(text/event-stream)로 발행한다. 이메일 분기 시 "
    "`interrupt` 이벤트(초안)에서 멈추며, `.../weakness-agent/resume` 로 승인/취소해 재개한다. "
    "SSE 스트림이라 ApiResponse 로 감싸지 않는다.",
    responses=NOT_FOUND,
)
async def run_weakness_agent(
    company_id: CompanyIdPath,
    session_id: SessionIdPath,
    body: WeaknessAgentRequest,
    service: AgentServiceDep,
) -> StreamingResponse:
    return _agent_stream_response(
        service.run_stream(company_id, session_id, body.bid_notice_id)
    )


@router.post(
    "/{session_id}/weakness-agent/resume",
    summary="회사 약점 해결 에이전트 HITL 재개 (스트리밍)",
    description="이메일 서브그래프의 협업 제안 메일 발송을 승인/취소해 에이전트를 재개한다. "
    "run 스트림과 같은 세션(thread)을 이어받아 나머지 노드 상태를 SSE 로 발행한다.",
    responses=NOT_FOUND,
)
async def resume_weakness_agent(
    company_id: CompanyIdPath,
    session_id: SessionIdPath,
    body: WeaknessAgentResumeRequest,
    service: AgentServiceDep,
) -> StreamingResponse:
    return _agent_stream_response(
        service.resume_stream(company_id, session_id, body.approved)
    )
