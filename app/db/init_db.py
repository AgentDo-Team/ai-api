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

# BM25 렉시컬 인덱스 (pg_search). content 를 한국어 형태소 분석기(korean_lindera)로
# 색인하고, bid_notice_id 를 함께 색인해 공고 필터가 인덱스에 푸시다운되도록 한다
# (2차 소프트필터의 배치 BM25 검색이 이 인덱스를 쓴다). dense(HNSW)와 함께 하이브리드 구성.
LEXICAL_INDEXES = (
    """CREATE INDEX IF NOT EXISTS idx_chunks_bm25 ON chunks
       USING bm25 (id, content, bid_notice_id)
       WITH (key_field='id', text_fields='{"content":{"tokenizer":{"type":"korean_lindera"}}}')""",
)

# create_all 은 기존 테이블에 새 컬럼을 추가하지 않으므로 호환 가능한 스키마 보강은
# 명시적으로 적용한다. 별도 마이그레이션 도구 도입 전까지 사용하는 최소 변경 목록이다.
SCHEMA_UPGRADES = (
    "ALTER TABLE search_sets ADD COLUMN IF NOT EXISTS failure_reason TEXT",
)


async def init_db() -> None:
    async with engine.begin() as conn:
        # 1. 확장 생성 (vector 타입 / bm25 인덱스 사용 전 반드시 필요)
        await conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
        await conn.execute(text("CREATE EXTENSION IF NOT EXISTS pg_search"))

        # 2. 전체 테이블 생성
        await conn.run_sync(SQLModel.metadata.create_all)

        for stmt in SCHEMA_UPGRADES:
            await conn.execute(text(stmt))

        # 3. 벡터(HNSW) 인덱스 생성
        for stmt in VECTOR_INDEXES:
            await conn.execute(text(stmt))

        # 4. BM25 렉시컬 인덱스 생성
        for stmt in LEXICAL_INDEXES:
            await conn.execute(text(stmt))

    await engine.dispose()
    print("DB 스키마 초기화 완료")


if __name__ == "__main__":
    asyncio.run(init_db())
