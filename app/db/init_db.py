"""DB 스키마 초기화 스크립트.

실행 순서:
  1. 확장 생성: vector(pgvector) + pg_search(BM25)
  2. SQLModel 메타데이터 기반 전체 테이블 생성 (create_all)
  3. 벡터 컬럼(HNSW, cosine) 인덱스 생성
  4. BM25 렉시컬 인덱스 생성 (chunks.content, 한국어 형태소 분석기)

사용법:
  uv run python -m app.db.init_db
"""

import asyncio

from sqlalchemy import text
from sqlmodel import SQLModel

# 모든 모델을 import 하여 SQLModel.metadata 에 테이블을 등록한다.
import app.db.models  # noqa: F401
from app.db.session import engine

# NULL=미임베딩 벡터 컬럼에 대한 HNSW(cosine) 인덱스
VECTOR_INDEXES = (
    "CREATE INDEX IF NOT EXISTS idx_chunks_embedding "
    "ON chunks USING hnsw (embedding vector_cosine_ops)",
    "CREATE INDEX IF NOT EXISTS idx_company_projects_embedding "
    "ON company_projects USING hnsw (embedding vector_cosine_ops)",
    "CREATE INDEX IF NOT EXISTS idx_company_profiles_embedding "
    "ON company_profiles USING hnsw (embedding vector_cosine_ops)",
    "CREATE INDEX IF NOT EXISTS idx_eval_criteria_references_embedding "
    "ON eval_criteria_references USING hnsw (embedding vector_cosine_ops)",
)

# BM25 렉시컬 인덱스 (pg_search v2 API). content 컬럼을 한국어 형태소 분석기(pdb.lindera)로
# 캐스팅해 색인하고, bid_notice_id 는 필터 푸시다운을 위해 함께 색인한다.
# dense(HNSW)와 함께 하이브리드 검색을 구성한다.
LEXICAL_INDEXES = (
    """CREATE INDEX IF NOT EXISTS idx_chunks_bm25 ON chunks
       USING bm25 (id, bid_notice_id, (content::pdb.lindera(korean)))
       WITH (key_field='id')""",
)

# BM25 렉시컬 인덱스 (pg_search). content 원문을 한국어 형태소 분석기(korean_lindera)로
# 색인해 정확 용어 매칭에 사용한다. dense(HNSW)와 함께 하이브리드 검색을 구성.
LEXICAL_INDEXES = (
    """CREATE INDEX IF NOT EXISTS idx_chunks_bm25 ON chunks
       USING bm25 (id, content)
       WITH (key_field='id', text_fields='{"content":{"tokenizer":{"type":"korean_lindera"}}}')""",
)


async def init_db() -> None:
    async with engine.begin() as conn:
        # 1. 확장 생성 (vector 타입 / bm25 인덱스 사용 전 반드시 필요)
        await conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
        await conn.execute(text("CREATE EXTENSION IF NOT EXISTS pg_search"))

        # 2. 전체 테이블 생성
        await conn.run_sync(SQLModel.metadata.create_all)

        # 3. 벡터(HNSW) 인덱스 생성
        for stmt in VECTOR_INDEXES:
            await conn.execute(text(stmt))

        # 4. BM25 렉시컬 인덱스 생성
        for stmt in LEXICAL_INDEXES:
            await conn.execute(text(stmt))

    await engine.dispose()
    print("✅ DB 스키마 초기화 완료")


if __name__ == "__main__":
    asyncio.run(init_db())
