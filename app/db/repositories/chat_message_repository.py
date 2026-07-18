"""챗봇 메시지(chat_messages) 영속성 계층.

DB 접근만 담당한다. commit 은 서비스(app/services/chat_service.py)의 몫이다.
메시지는 기존 chat_messages 테이블(search_set_id/role/content)에 쌓인다.
"""

from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.db.models.analysis import ChatMessage


class ChatMessageRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def add(self, message: ChatMessage) -> ChatMessage:
        self.session.add(message)
        await self.session.flush()  # id 채우기 (commit 은 서비스에서)
        return message

    async def list_by_search_set(self, search_set_id: int) -> list[ChatMessage]:
        """세션의 메시지를 시간순(오래된→최신)으로 반환한다. 이전 세션 연결용."""
        result = await self.session.exec(
            select(ChatMessage)
            .where(ChatMessage.search_set_id == search_set_id)
            .order_by(ChatMessage.id)
        )
        return list(result.all())
