from __future__ import annotations

from sqlalchemy import text
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.db.models.bid import Chunk

"""bid_notice 청크 영속성 계층.

dense_search/sparse_search 는 하이브리드 검색(app/rag/retrievers/hybrid_search.py)의
원재료가 되는 순위 리스트만 반환한다. RRF 융합 등 검색 로직 자체는 여기에 두지 않는다.
"""


class ChunkRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
       
    async def add_all(self, chunks: list[Chunk]) -> None:
        self.session.add_all(chunks)
        await self.session.flush()
    
    async def get_unembedded_chunks(self, bid_notice_id: int) -> list[Chunk]:
        """특정 공고에서 아직 임베딩되지 않은 청크 목록을 순서대로 조회합니다."""
        stmt = select(Chunk).where(
            Chunk.bid_notice_id == bid_notice_id,
            Chunk.embedding.is_(None)
        ).order_by(Chunk.chunk_index)
        
        result = await self.session.exec(stmt)
        return list(result.all())

    async def get_all_unembedded_chunks(self, limit: int = 100) -> list[Chunk]:
        """공고와 무관하게 임베딩되지 않은 청크들을 일괄 조회합니다 (스케줄러 배치용)."""
        stmt = select(Chunk).where(
            Chunk.embedding.is_(None)
        ).order_by(Chunk.id).limit(limit)
        
        result = await self.session.exec(stmt)
        return list(result.all())

    async def update_embeddings(
        self,
        chunks: list[Chunk],
        vectors: list[list[float]]
    ):
        """청크 객체에 벡터 값을 할당하여 세션에 추가합니다."""
        # chunk와 vector의 개수가 일치하므로 zip으로 묶어서 매핑
        for chunk, vector in zip(chunks, vectors):
            chunk.embedding = vector

        # 객체의 속성만 변경하고 session.add_all을 호출해 두면,
        # 이후 서비스 레이어에서 session.commit() 호출 시 한 번에 UPDATE 쿼리가 날아감
        self.session.add_all(chunks)

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
        self,
        bid_notice_id: int,
        query_embedding: list[float],
        limit: int = 10,
        l_topics: list[str] | None = None,
    ) -> list[tuple[Chunk, float]]:
        """코사인 거리 오름차순(가까울수록 유사). embedding 이 NULL 인 청크는 제외.

        l_topics 를 주면 chunk_metadata.l_topic(개요/요구사항/평가기준/기타)이
        그 목록에 드는 청크로만 좁힌다(2차 소프트필터의 도메인 스코프용).
        """
        distance = Chunk.embedding.cosine_distance(query_embedding).label("distance")
        stmt = (
            select(Chunk, distance)
            .where(Chunk.bid_notice_id == bid_notice_id, Chunk.embedding.is_not(None))
        )
        if l_topics:
            stmt = stmt.where(Chunk.chunk_metadata["l_topic"].astext.in_(l_topics))
        result = await self.session.exec(stmt.order_by(distance).limit(limit))
        return [(row[0], row[1]) for row in result.all()]

    async def sparse_search(
        self,
        bid_notice_id: int,
        query_text: str,
        limit: int = 10,
        l_topics: list[str] | None = None,
    ) -> list[tuple[Chunk, float]]:
        """BM25 스코어(pg_search) 내림차순. idx_chunks_bm25 인덱스를 사용한다.

        l_topics 를 주면 chunk_metadata.l_topic 이 그 목록에 드는 청크로만 좁힌다.
        """
        topic_clause = "AND metadata->>'l_topic' = ANY(:l_topics)" if l_topics else ""
        rows = await self.session.execute(
            text(
                f"""
                SELECT id, pdb.score(id) AS rank
                FROM chunks
                WHERE bid_notice_id = :bid_notice_id
                  AND content ||| :query_text
                  {topic_clause}
                ORDER BY rank DESC
                LIMIT :limit
                """
            ),
            {
                "bid_notice_id": bid_notice_id,
                "query_text": query_text,
                "limit": limit,
                **({"l_topics": l_topics} if l_topics else {}),
            },
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
