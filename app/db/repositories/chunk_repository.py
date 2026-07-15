"""bid_notice 청크 영속성 계층.

dense_search/sparse_search 는 하이브리드 검색(app/rag/retrievers/hybrid_search.py)의
원재료가 되는 순위 리스트만 반환한다. RRF 융합 등 검색 로직 자체는 여기에 두지 않는다.
"""

from __future__ import annotations

from sqlalchemy import text
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.db.models.bid import Chunk


class ChunkRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def add(self, chunk: Chunk) -> Chunk:
        self.session.add(chunk)
        await self.session.flush()
        return chunk

    async def bulk_add(self, chunks: list[Chunk]) -> list[Chunk]:
        for chunk in chunks:
            self.session.add(chunk)
        await self.session.flush()
        return chunks

    async def get(self, chunk_id: int) -> Chunk | None:
        return await self.session.get(Chunk, chunk_id)

    async def list_by_bid_notice(self, bid_notice_id: int) -> list[Chunk]:
        result = await self.session.exec(
            select(Chunk)
            .where(Chunk.bid_notice_id == bid_notice_id)
            .order_by(Chunk.chunk_index)
        )
        return list(result.all())

    async def dense_search(
        self, bid_notice_id: int, query_embedding: list[float], limit: int = 10
    ) -> list[tuple[Chunk, float]]:
        """코사인 거리 오름차순(가까울수록 유사). embedding 이 NULL 인 청크는 제외."""
        distance = Chunk.embedding.cosine_distance(query_embedding).label("distance")
        result = await self.session.exec(
            select(Chunk, distance)
            .where(Chunk.bid_notice_id == bid_notice_id, Chunk.embedding.is_not(None))
            .order_by(distance)
            .limit(limit)
        )
        return [(row[0], row[1]) for row in result.all()]

    async def sparse_search(
        self, bid_notice_id: int, query_text: str, limit: int = 10
    ) -> list[tuple[Chunk, float]]:
        """BM25 스코어(pg_search) 내림차순. idx_chunks_bm25 인덱스를 사용한다."""
        rows = await self.session.execute(
            text(
                """
                SELECT id, pdb.score(id) AS rank
                FROM chunks
                WHERE bid_notice_id = :bid_notice_id
                  AND content ||| :query_text
                ORDER BY rank DESC
                LIMIT :limit
                """
            ),
            {"bid_notice_id": bid_notice_id, "query_text": query_text, "limit": limit},
        )
        ranked = [(row.id, row.rank) for row in rows]
        if not ranked:
            return []

        chunks = {chunk_id: await self.get(chunk_id) for chunk_id, _ in ranked}
        return [(chunks[chunk_id], rank) for chunk_id, rank in ranked if chunks[chunk_id] is not None]

    async def delete_by_bid_notice(self, bid_notice_id: int) -> None:
        chunks = await self.list_by_bid_notice(bid_notice_id)
        for chunk in chunks:
            await self.session.delete(chunk)
