"""DB 스키마 초기화 스크립트.

실행 순서:
  1. pgvector 확장(vector) 생성
  2. SQLModel 메타데이터 기반 전체 테이블 생성 (create_all)
  3. 벡터 컬럼(HNSW, cosine) 인덱스 생성

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
)


async def init_db() -> None:
    async with engine.begin() as conn:
        # 1. pgvector 확장 (vector 타입 사용 전 반드시 필요)
        await conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))

        # 2. 전체 테이블 생성
        await conn.run_sync(SQLModel.metadata.create_all)

        # 3. 벡터 인덱스 생성
        for stmt in VECTOR_INDEXES:
            await conn.execute(text(stmt))

    await engine.dispose()
    print("✅ DB 스키마 초기화 완료")


if __name__ == "__main__":
    asyncio.run(init_db())
