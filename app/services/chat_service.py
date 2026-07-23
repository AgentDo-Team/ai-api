from collections.abc import AsyncIterator

from langchain_core.output_parsers import StrOutputParser
from langchain_core.prompts import ChatPromptTemplate
from langchain_openai import ChatOpenAI
from openai import AsyncOpenAI
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.common.exceptions import AppException
from app.core.config import settings
from app.db.models.analysis import ChatMessage
from app.db.models.bid import Chunk
from app.db.models.search import SearchSet
from app.db.repositories.chat_message_repository import ChatMessageRepository
from app.db.repositories.company_repository import (
    CompanyProfileRepository,
    CompanyProjectRepository,
)
from app.db.repositories.search_set_repository import SearchSetRepository
from app.services.embedding_service import profile_text, project_text

my_template = ChatPromptTemplate.from_messages(
    [
        ("system", "입찰공고를 추천해주는 챗봇이야"),
        (
            "human",
            "{question}에 대해 5줄 이내로 쉽게 설명해줘, \n"
            "이때 {docs_context} 와 {company_context} 내용을 참고해서 설명해줘",
        ),
    ]
)

parser = StrOutputParser()

gpt_model = ChatOpenAI(model=settings.llm_model, temperature=0.2)

my_gpt_chain = my_template | gpt_model | parser

_openai_client = AsyncOpenAI(api_key=settings.openai_api_key)


async def embedding(text: str) -> list[float]:
    embed_res = await _openai_client.embeddings.create(
        model=settings.embedding_model,
        input=text,
        dimensions=settings.embedding_dim,
    )
    return embed_res.data[0].embedding


async def dense_search(
    session: AsyncSession, bid_notice_id: int, question_embedding: list[float]
) -> list[Chunk]:
    dist = Chunk.embedding.cosine_distance(question_embedding).label("distance")
    stmt = (
        select(Chunk, dist)
        .where(Chunk.bid_notice_id == bid_notice_id, Chunk.embedding.is_not(None))
        .order_by(dist)
        .limit(5)
    )
    result = await session.exec(stmt)
    return [row[0] for row in result.all()]


async def build_company_context(session: AsyncSession, company_id: int) -> str:
    profile_repo = CompanyProfileRepository(session)
    project_repo = CompanyProjectRepository(session)

    profile = await profile_repo.get_by_company_id(company_id)
    profile_str = profile_text(profile) if profile else "(등록된 프로필 없음)"

    projects = await project_repo.list_by_company(company_id, limit=20)
    projects_str = "\n".join(project_text(p) for p in projects) or "(등록된 실적 없음)"

    return f"{profile_str}\n\n{projects_str}"

class ChatService:
    def __init__(
        self,
        session: AsyncSession,
        search_set_repo: SearchSetRepository,
        chat_message_repo: ChatMessageRepository,
    ) -> None:
        self.session = session
        self.search_set_repo = search_set_repo
        self.chat_message_repo = chat_message_repo

    async def _get_owned_session(
        self, company_id: int, session_id: int
    ) -> SearchSet:
        """세션을 조회하고 소유 회사를 검증한다. 없거나 남의 것이면 404."""
        search_set = await self.search_set_repo.get(session_id)
        if search_set is None or search_set.company_id != company_id:
            raise AppException("채팅 세션을 찾을 수 없습니다.", status_code=404)
        return search_set

    async def list_sessions(self, company_id: int) -> list[SearchSet]:
        return await self.search_set_repo.list_by_company(company_id)

    async def delete_session(self, company_id: int, session_id: int) -> None:
        search_set = await self._get_owned_session(company_id, session_id)
        await self.search_set_repo.delete(search_set)
        await self.session.commit()

    async def get_messages(
        self, company_id: int, session_id: int
    ) -> list[ChatMessage]:
        """이전 세션의 대화 내역(이전 세션 연결)."""
        await self._get_owned_session(company_id, session_id)
        return await self.chat_message_repo.list_by_search_set(session_id)
    
    async def chat(
        self,
        company_id: int,
        session_id: int,
        question: str,
        bid_notice_id: int | None = None,
    ) -> ChatMessage:
        await self._get_owned_session(company_id, session_id)

        user_message = ChatMessage( search_set_id=session_id, role="user", content=question)
        await self.chat_message_repo.add(user_message)

        question_embedding = await embedding(question)
        if bid_notice_id is not None:
            chunks = await dense_search(self.session, bid_notice_id, question_embedding)
            docs_context = "\n\n".join(c.content or "" for c in chunks) or "(관련 공고 내용 없음)"
        else:
            docs_context = "(지정된 공고 없음)" 
        company_context = await build_company_context(self.session, company_id)

        answer = await my_gpt_chain.ainvoke(
            {
                "question": question,
                "docs_context": docs_context,
                "company_context": company_context,
            }
        )

        assistant_message = ChatMessage(
            search_set_id=session_id, role="assistant", content=answer
        )
        await self.chat_message_repo.add(assistant_message)
        await self.session.commit()
        await self.session.refresh(assistant_message)
        return assistant_message

    async def chat_stream(
        self,
        company_id: int,
        session_id: int,
        question: str,
        bid_notice_id: int | None = None,
    ) -> AsyncIterator[dict]:
        await self._get_owned_session(company_id, session_id)

        user_message = ChatMessage(
            search_set_id=session_id, role="user", content=question
        )
        await self.chat_message_repo.add(user_message)

        question_embedding = await embedding(question)
        if bid_notice_id is not None:
            chunks = await dense_search(
                self.session, bid_notice_id, question_embedding
            )
            docs_context = "\n\n".join(c.content or "" for c in chunks) or "(관련 공고 내용 없음)"
        else:
            docs_context = "(지정된 공고 없음)"
        company_context = await build_company_context(self.session, company_id)

        parts: list[str] = []
        async for token in my_gpt_chain.astream(
            {
                "question": question,
                "docs_context": docs_context,
                "company_context": company_context,
            }
        ):
            if not token:
                continue
            parts.append(token)
            yield {"type": "delta", "content": token}

        assistant_message = ChatMessage(
            search_set_id=session_id, role="assistant", content="".join(parts)
        )
        await self.chat_message_repo.add(assistant_message)
        await self.session.commit()
        await self.session.refresh(assistant_message)
        yield {"type": "done", "message_id": assistant_message.id}
