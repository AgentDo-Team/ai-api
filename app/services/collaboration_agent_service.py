"""회사 약점 해결 에이전트 오케스트레이션 서비스.

메인 그래프(app.agents.collaboration_agent)를 스트리밍 실행하고, 각 노드가 발행하는
커스텀 상태 이벤트를 dict 로 흘려보낸다. 라우터는 이 dict 를 SSE 로 직렬화한다
(기존 ChatService.chat_stream 과 같은 패턴).

HITL:
  이메일 분기에서 human_review 의 interrupt 가 걸리면 run_stream 은 interrupt 이벤트를
  내보내고 멈춘다. 프론트가 승인/취소하면 resume_stream 이 같은 thread_id 로 재개한다.

주의: 그래프는 InMemorySaver(단일 프로세스 메모리) 로 컴파일된 모듈 싱글턴이라
run_stream 과 resume_stream 이 같은 프로세스에서 같은 thread_id 를 공유해야 재개된다.
멀티 워커/재시작 시 thread 상태가 유실되므로, 운영 확장 시 Postgres checkpointer 로 교체해야 한다.
"""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator

from langgraph.types import Command
from sqlmodel.ext.asyncio.session import AsyncSession

from app.agents.collaboration_agent.graph import build_collaboration_agent_graph
from app.common.exceptions import AppException
from app.db.models.analysis import ChatMessage
from app.db.repositories.chat_message_repository import ChatMessageRepository
from app.db.repositories.search_set_repository import SearchSetRepository

logger = logging.getLogger(__name__)

# 그래프는 무겁고 checkpointer 상태(InMemorySaver)를 요청 간 유지해야 하므로 모듈 싱글턴으로 1회만 빌드한다.
_graph = None


def _get_graph():
    global _graph
    if _graph is None:
        _graph = build_collaboration_agent_graph()
    return _graph


class CollaborationAgentService:
    def __init__(
        self,
        session: AsyncSession,
        search_set_repo: SearchSetRepository,
        chat_message_repo: ChatMessageRepository,
    ) -> None:
        self.session = session
        self.search_set_repo = search_set_repo
        self.chat_message_repo = chat_message_repo

    async def _verify_owned(self, company_id: int, session_id: int) -> None:
        """세션 소유권 검증. 없거나 남의 것이면 404."""
        search_set = await self.search_set_repo.get(session_id)
        if search_set is None or search_set.company_id != company_id:
            raise AppException("채팅 세션을 찾을 수 없습니다.", status_code=404)

    @staticmethod
    def _config(session_id: int, bid_notice_id: int) -> dict:
        """thread_id 에 bid_notice_id 까지 포함해야 한다.

        session_id(검색 세트) 하나에서 여러 공고가 추천되므로, bid_notice_id 를 빼면
        같은 세션에서 공고 A 를 이메일 HITL interrupt 로 멈춰둔 채 공고 B 로 다시
        run_stream 을 호출했을 때 체크포인트가 뒤섞여, resume 시 엉뚱한 공고/협력사에
        메일이 발송될 위험이 있다.
        """
        return {
            "configurable": {"thread_id": f"weakness-agent-{session_id}-{bid_notice_id}"}
        }

    async def run_stream(
        self, company_id: int, session_id: int, bid_notice_id: int
    ) -> AsyncIterator[dict]:
        """에이전트를 시작해 노드 상태를 스트리밍한다. 이메일 분기 시 interrupt 에서 멈춘다."""
        await self._verify_owned(company_id, session_id)
        config = self._config(session_id, bid_notice_id)
        inputs = {
            "company_id": company_id,
            "search_set_id": session_id,
            "bid_notice_id": bid_notice_id,
        }

        async for mode, chunk in self._astream(inputs, config):
            if mode == "custom":
                yield chunk
            elif self._is_interrupt(mode, chunk):
                # 이메일 HITL: 초안을 노출하고 스트림을 닫는다. 승인/취소는 resume 로.
                draft = self._interrupt_draft(chunk)
                yield {
                    "type": "interrupt",
                    "graph": "email",
                    "label": "이메일 허락 대기 중",
                    "draft": draft,
                }
                return

        # interrupt 없이 끝났으면(검색 분기, 또는 이메일 없이 종료) 결과를 확정한다.
        async for event in self._finalize(session_id, config):
            yield event

    async def resume_stream(
        self, company_id: int, session_id: int, bid_notice_id: int, approved: bool
    ) -> AsyncIterator[dict]:
        """HITL interrupt 이후 승인/취소로 재개하고 나머지 노드 상태를 스트리밍한다.

        run_stream 을 호출할 때와 같은 bid_notice_id 를 넘겨야 같은 thread(체크포인트)를
        찾아 재개할 수 있다.
        """
        await self._verify_owned(company_id, session_id)
        config = self._config(session_id, bid_notice_id)

        async for mode, chunk in self._astream(
            Command(resume={"approved": approved}), config
        ):
            if mode == "custom":
                yield chunk

        async for event in self._finalize(session_id, config):
            yield event

    # --------------------------------------------------------------------- #
    # 내부 헬퍼
    # --------------------------------------------------------------------- #
    async def _astream(self, payload, config):
        """(mode, chunk) 튜플만 넘겨주는 astream 래퍼. subgraphs 네임스페이스는 버린다."""
        async for _namespace, mode, chunk in _get_graph().astream(
            payload,
            config=config,
            stream_mode=["custom", "updates"],
            subgraphs=True,
        ):
            yield mode, chunk

    @staticmethod
    def _is_interrupt(mode: str, chunk) -> bool:
        return (
            mode == "updates"
            and isinstance(chunk, dict)
            and "__interrupt__" in chunk
        )

    @staticmethod
    def _interrupt_draft(chunk) -> dict:
        value = chunk["__interrupt__"][0].value
        return value.get("draft", {}) if isinstance(value, dict) else {}

    async def _finalize(self, session_id: int, config) -> AsyncIterator[dict]:
        """최종 상태를 읽어 assistant 메시지로 저장하고 done 이벤트를 낸다."""
        state = await _get_graph().aget_state(config)
        values = state.values
        branch = values.get("branch")

        if branch == "email":
            status = values.get("status")
            if status == "sent":
                content = f"협업 제안 메일을 {values.get('to')} 주소로 발송했습니다."
            elif status == "cancelled":
                content = "협업 제안 메일 발송을 취소했습니다."
            else:
                content = "협업 제안 메일 초안을 작성했습니다."
            done = {"type": "done", "status": status or "drafted"}
        else:
            content = values.get("report") or "추천 리포트를 생성하지 못했습니다."
            done = {"type": "done", "status": "report", "report": content}

        message = ChatMessage(
            search_set_id=session_id, role="assistant", content=content
        )
        await self.chat_message_repo.add(message)
        await self.session.commit()
        await self.session.refresh(message)

        done["message_id"] = message.id
        yield done
