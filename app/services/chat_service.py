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
#
# LLM 체인 관련
#
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

#
# RAG 관련 함수
#
async def embedding(text: str) -> list[float]:
    # 질문을 임베딩한다 (랭체인 미사용 버전)
    embed_res = await _openai_client.embeddings.create(
        model=settings.embedding_model,
        input=text,
        dimensions=settings.embedding_dim,
    )
    return embed_res.data[0].embedding


async def dense_search(
    session: AsyncSession, bid_notice_id: int, question_embedding: list[float]
) -> list[Chunk]:
    # 공고의 청크 중 질문과 가장 가까운 상위 5건을 코사인 거리로 검색한다
    # .cosine_distance(other) 는 내부적으로 PostgreSQL 의 <=> 연산자(코사인 거리)로 변환된다.
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

#
# 챗봇 서비스 클래스
#
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

    # 해당 채팅의 주인인지 확인
    async def _get_owned_session(
        self, company_id: int, session_id: int
    ) -> SearchSet:
        """세션을 조회하고 소유 회사를 검증한다. 없거나 남의 것이면 404."""
        search_set = await self.search_set_repo.get(session_id)
        # 다른 회사의 세션은 존재하지 않는 것으로 취급한다.
        if search_set is None or search_set.company_id != company_id:
            raise AppException("채팅 세션을 찾을 수 없습니다.", status_code=404)
        return search_set

    # 채팅 리스트 확인
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
    
    #
    # 채팅 관련
    # 


    # 지금은 얘 안씀 chat_stream 으로 쓰기 때문에 삭제해도 무방하나, 이후 프로젝트 때 참고하려고 남겨둠
    async def chat(
        self,
        company_id: int,
        session_id: int,
        question: str,
        bid_notice_id: int | None = None,
    ) -> ChatMessage:
        # 질문을 저장하고, RAG 로 답변을 생성해 저장한 뒤 assistant 메시지를 반환한다.
        await self._get_owned_session(company_id, session_id)

        # 1) 사용자 question 디비에 저장
        user_message = ChatMessage( search_set_id=session_id, role="user", content=question)
        await self.chat_message_repo.add(user_message)

        # 2) LLM 질의 시 추가할 문서 청크,회사 정보 구성
        question_embedding = await embedding(question)
        if bid_notice_id is not None:
            chunks = await dense_search(self.session, bid_notice_id, question_embedding)
            docs_context = "\n\n".join(c.content or "" for c in chunks) or "(관련 공고 내용 없음)"
        else:
            docs_context = "(지정된 공고 없음)" #이거 필요 없는데 없으면 테스트 팅겨서 그냥 둠
        company_context = await build_company_context(self.session, company_id)

        # 3) 답변 생성 (print 대신 반환값 사용)
        answer = await my_gpt_chain.ainvoke(
            {
                "question": question,
                "docs_context": docs_context,
                "company_context": company_context,
            }
        )

        # 4) 답변 저장 후 반환
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
        """
        참고
        이벤트(dict) 종류:
        {"type": "delta", "content": <토큰>} — 생성된 부분 문자열
        {"type": "done",  "message_id": <int>} — 저장 완료된 ai 응답 메시지 id
        """
        await self._get_owned_session(company_id, session_id)

        # 1. 사용자 질문 저장
        user_message = ChatMessage(
            search_set_id=session_id, role="user", content=question
        )
        await self.chat_message_repo.add(user_message)

        # 2. RAG 컨텍스트 구성
        question_embedding = await embedding(question)
        if bid_notice_id is not None:
            chunks = await dense_search(
                self.session, bid_notice_id, question_embedding
            )
            docs_context = "\n\n".join(c.content or "" for c in chunks) or "(관련 공고 내용 없음)"
        else:
            docs_context = "(지정된 공고 없음)"
        company_context = await build_company_context(self.session, company_id)

        # 3. astream 을 사용하여 답변을 토큰 단위로 스트리밍하며 누적
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

        # 4. 답변 저장 후 done 이벤트로 message_id 전달
        assistant_message = ChatMessage(
            search_set_id=session_id, role="assistant", content="".join(parts)
        )
        # DB 커밋 관련
        await self.chat_message_repo.add(assistant_message)
        await self.session.commit()
        await self.session.refresh(assistant_message)
        # yield로 내보낸 값들은 호출하는 쪽에서 async for로 하나씩 꺼내 씁니다
        yield {"type": "done", "message_id": assistant_message.id}
