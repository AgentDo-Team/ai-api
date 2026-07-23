import asyncio

from sqlalchemy import text
from sqlmodel import SQLModel

# 모든 모델을 import 하여 SQLModel.metadata 에 테이블을 등록한다.
import app.db.models  # noqa: F401
from app.db.session import engine

COLUMN_MIGRATIONS = (
    "ALTER TABLE search_sets ADD COLUMN IF NOT EXISTS progress_current INTEGER",
    "ALTER TABLE search_sets ADD COLUMN IF NOT EXISTS progress_total INTEGER",
    "ALTER TABLE partners ADD COLUMN IF NOT EXISTS email VARCHAR(255)",
)

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

LEXICAL_INDEXES = (
    """CREATE INDEX IF NOT EXISTS idx_chunks_bm25 ON chunks
       USING bm25 (id, content, bid_notice_id)
       WITH (key_field='id', text_fields='{"content":{"tokenizer":{"type":"korean_lindera"}}}')""",
)

SCHEMA_UPGRADES = (
    "ALTER TABLE search_sets ADD COLUMN IF NOT EXISTS failure_reason TEXT",
)


async def init_db() -> None:
    async with engine.begin() as conn:
        await conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
        await conn.execute(text("CREATE EXTENSION IF NOT EXISTS pg_search"))

        await conn.run_sync(SQLModel.metadata.create_all)

        for stmt in SCHEMA_UPGRADES:
            await conn.execute(text(stmt))
        for stmt in COLUMN_MIGRATIONS:
            await conn.execute(text(stmt))
        for stmt in VECTOR_INDEXES:
            await conn.execute(text(stmt))
        for stmt in LEXICAL_INDEXES:
            await conn.execute(text(stmt))

    await engine.dispose()
    print("DB 스키마 초기화 완료")


if __name__ == "__main__":
    asyncio.run(init_db())
