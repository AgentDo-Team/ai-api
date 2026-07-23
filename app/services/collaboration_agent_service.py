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
        search_set = await self.search_set_repo.get(session_id)
        if search_set is None or search_set.company_id != company_id:
            raise AppException("채팅 세션을 찾을 수 없습니다.", status_code=404)

    @staticmethod
    def _config(session_id: int, bid_notice_id: int) -> dict:
        return {
            "configurable": {"thread_id": f"weakness-agent-{session_id}-{bid_notice_id}"}
        }

    async def run_stream(
        self, company_id: int, session_id: int, bid_notice_id: int
    ) -> AsyncIterator[dict]:
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
                draft = self._interrupt_draft(chunk)
                yield {
                    "type": "interrupt",
                    "graph": "email",
                    "label": "이메일 허락 대기 중",
                    "draft": draft,
                }
                return

        async for event in self._finalize(session_id, config):
            yield event

    async def resume_stream(
        self, company_id: int, session_id: int, bid_notice_id: int, approved: bool
    ) -> AsyncIterator[dict]:
        await self._verify_owned(company_id, session_id)
        config = self._config(session_id, bid_notice_id)

        async for mode, chunk in self._astream(
            Command(resume={"approved": approved}), config
        ):
            if mode == "custom":
                yield chunk

        async for event in self._finalize(session_id, config):
            yield event

    async def _astream(self, payload, config):
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
