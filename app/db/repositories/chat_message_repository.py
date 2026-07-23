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
        result = await self.session.exec(
            select(ChatMessage)
            .where(ChatMessage.search_set_id == search_set_id)
            .order_by(ChatMessage.id)
        )
        return list(result.all())
