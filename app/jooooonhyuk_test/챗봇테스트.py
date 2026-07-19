"""
uv run python -m app.jooooonhyuk_test.챗봇테스트
"""

#AI 관련
from langchain_openai import ChatOpenAI
from openai import AsyncOpenAI # OpenAPI 는 동기라 Fast API에서는 비동기로 쓰자
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import StrOutputParser
from app.services.embedding_service import profile_text, project_text

#SQL 관련
from app.db.models.bid import Chunk #청크
from app.db.session import async_session_factory
from app.db.repositories.company_repository import CompanyProfileRepository, CompanyProjectRepository
from sqlmodel.ext.asyncio.session import AsyncSession
from sqlmodel import select

from app.core.config import settings #env 값 가져와줌

my_template= ChatPromptTemplate.from_messages([
    ("system", "입찰공고를 추천해주는 챗봇이야"),
    ("human", "{question}에 대해 5줄 이내로 쉽게 설명해줘, \n"
    "이때 {docs_context} 와 {company_context} 내용을 참고해서 설명해줘")
])

parser = StrOutputParser()

gpt_model = ChatOpenAI(
    model="gpt-4o-mini",
    temperature=0.2,
)

my_gpt_chain = my_template | gpt_model | parser

client= AsyncOpenAI()

# 임베딩 (랭체인 사용하지 않은 버전)
async def embedding(text:str) -> list[float]:
    embed_res = await client.embeddings.create(
        model='text-embedding-3-small',
        input=text,
        dimensions=settings.embedding_dim
    )
    return embed_res.data[0].embedding

# 상위 5건 백터 검색
async def dense_search(bid_notice_id: int,question_embedding: list[float])->list[tuple[Chunk,float]]:
    # .cosine_distance(other)를 호출하면 내부적으로 PostgreSQL의 <=> 연산자(코사인 거리)로 변환
    dist = Chunk.embedding.cosine_distance(question_embedding).label("distance") # distance 라는 라벨 붙이기
    stmt = (
        select(Chunk,dist)
        .where(Chunk.bid_notice_id==bid_notice_id,Chunk.embedding.is_not(None))
    )
    async with async_session_factory() as session:
        result = await session.exec(stmt.order_by(dist).limit(5)) #거리기준 상위 5개
        return [row[0] for row in result.all()] #[Chunk]
    
# 회사 정보 가져오기
async def build_company_context(session: AsyncSession, company_id: int) -> str:
    profile_repo = CompanyProfileRepository(session)
    project_repo = CompanyProjectRepository(session)

    # 1) 프로필 조회 (없을 수 있음)
    profile = await profile_repo.get_by_company_id(company_id)
    profile_str = profile_text(profile) if profile else "(등록된 프로필 없음)"

    # 2) 프로젝트 목록 조회 (0건일 수 있음)
    projects = await project_repo.list_by_company(company_id, limit=20)
    projects_str = (
        "\n".join(project_text(p) for p in projects) or "(등록된 실적 없음)"
    )
    return f"{profile_str}\n\n{projects_str}"


# 챗봇 동작
async def chat_rag(bid_notice_id:int,company_id:int,question:str):
    question_embedding = await embedding(question)
    docs_context = await dense_search(bid_notice_id, question_embedding)
    async with async_session_factory() as session:
        company_context = await build_company_context(session, company_id)
    print(await my_gpt_chain.ainvoke({"question": question, "docs_context": docs_context,"company_context": company_context}))

# 로컬 테스팅용
if __name__=="__main__":
    import asyncio
    asyncio.run(chat_rag(3,8,"해당 프로젝트의 주제는 어떻게 되지?"))