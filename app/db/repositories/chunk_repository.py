from __future__ import annotations
from typing import Optional

from sqlalchemy import and_, or_, text
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.db.models.bid import Chunk

class ChunkRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
       
    async def add_all(self, chunks: list[Chunk]) -> None:
        self.session.add_all(chunks)
        await self.session.flush()
    
    async def get_unembedded_chunks(self, bid_notice_id: int) -> list[Chunk]:
        stmt = select(Chunk).where(
            Chunk.bid_notice_id == bid_notice_id,
            Chunk.embedding.is_(None)
        ).order_by(Chunk.chunk_index)
        
        result = await self.session.exec(stmt)
        return list(result.all())

    async def get_all_unembedded_chunks(self, limit: int = 100) -> list[Chunk]:
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
        for chunk, vector in zip(chunks, vectors):
            chunk.embedding = vector

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

        chunk_ids = [chunk_id for chunk_id, _ in ranked]
        fetched = await self.session.exec(select(Chunk).where(Chunk.id.in_(chunk_ids)))
        chunks = {chunk.id: chunk for chunk in fetched.all()}
        return [(chunks[cid], rank) for cid, rank in ranked if cid in chunks]

    async def sparse_search_multi(
        self,
        bid_notice_ids: list[int],
        query_text: str,
        per_notice_limit: int = 10,
        l_topics: list[str] | None = None,
    ) -> dict[int, list[tuple[Chunk, float]]]:
        
        if not bid_notice_ids or not query_text or not query_text.strip():
            return {}

        topic_clause = "AND metadata->>'l_topic' = ANY(:l_topics)" if l_topics else ""
        rows = (
            await self.session.execute(
                text(
                    f"""
                    SELECT id, bid_notice_id, score FROM (
                        SELECT id, bid_notice_id, pdb.score(id) AS score,
                               ROW_NUMBER() OVER (
                                   PARTITION BY bid_notice_id ORDER BY pdb.score(id) DESC
                               ) AS rn
                        FROM chunks
                        WHERE bid_notice_id = ANY(:ids)
                          AND content ||| :query_text
                          {topic_clause}
                    ) ranked
                    WHERE rn <= :per_notice_limit
                    """
                ),
                {
                    "ids": bid_notice_ids,
                    "query_text": query_text,
                    "per_notice_limit": per_notice_limit,
                    **({"l_topics": l_topics} if l_topics else {}),
                },
            )
        ).fetchall()
        if not rows:
            return {}

        chunk_ids = [row.id for row in rows]
        fetched = await self.session.exec(select(Chunk).where(Chunk.id.in_(chunk_ids)))
        chunk_by_id = {chunk.id: chunk for chunk in fetched.all()}

        result: dict[int, list[tuple[Chunk, float]]] = {}
        for row in rows:
            chunk = chunk_by_id.get(row.id)
            if chunk is not None:
                result.setdefault(row.bid_notice_id, []).append((chunk, row.score))
        for notice_id in result: 
            result[notice_id].sort(key=lambda pair: pair[1], reverse=True)
        return result

    async def delete_by_bid_notice(self, bid_notice_id: int) -> None:
        chunks = await self.list_by_bid_notice(bid_notice_id)
        for chunk in chunks:
            await self.session.delete(chunk)
            
    async def get_chunks_by_topics(
        self, 
        bid_notice_id: int, 
        l_topics: str = None, 
        s_topics: Optional[list[str]] = None
    ) -> dict:
        
        stmt = (
            select(Chunk)
            .where(Chunk.bid_notice_id == bid_notice_id)
            .where(
                Chunk.chunk_metadata["l_topic"].astext == l_topics,
                        Chunk.chunk_metadata["s_topic"].astext.in_(
                            s_topics
        )
    )
)
        result = await self.session.exec(stmt)
        chunks = result.all()
    
        parsed_data = {}
        
        for chunk in chunks:
            meta = chunk.chunk_metadata or {}
            
            l_topic = meta.get("l_topic", "개요")
            s_topic = meta.get("s_topic", "추진 내용")
            content = chunk.content or ""
            
            if l_topic not in parsed_data:
                parsed_data[l_topic] = {}
                
            if s_topic in parsed_data[l_topic]:
                parsed_data[l_topic][s_topic] += f"\n\n{content}"
            else:
                parsed_data[l_topic][s_topic] = content
                
        return parsed_data
