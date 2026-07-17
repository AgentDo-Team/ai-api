from __future__ import annotations
from typing import Optional

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

        # 매칭된 청크를 단일 IN 쿼리로 한 번에 조회한다(N+1 방지).
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
        """여러 공고에 대한 BM25 검색을 단일 쿼리로 수행해 공고별 상위 청크를 돌려준다.

        pg_search BM25 는 쿼리당 고정 오버헤드(~150ms)가 커서, 공고마다 sparse_search 를
        반복하면 매우 느리다. 윈도우 함수(ROW_NUMBER PARTITION BY bid_notice_id)로
        공고별 top-k 를 한 번에 뽑아 그 비용을 1회로 줄인다.

        반환: {bid_notice_id: [(Chunk, bm25_score)]} (공고별 점수 내림차순).
        """
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

        # 청크 본문을 단일 IN 쿼리로 조회
        chunk_ids = [row.id for row in rows]
        fetched = await self.session.exec(select(Chunk).where(Chunk.id.in_(chunk_ids)))
        chunk_by_id = {chunk.id: chunk for chunk in fetched.all()}

        result: dict[int, list[tuple[Chunk, float]]] = {}
        for row in rows:
            chunk = chunk_by_id.get(row.id)
            if chunk is not None:
                result.setdefault(row.bid_notice_id, []).append((chunk, row.score))
        for notice_id in result:  # 공고별 BM25 점수 내림차순 정렬
            result[notice_id].sort(key=lambda pair: pair[1], reverse=True)
        return result

    async def delete_by_bid_notice(self, bid_notice_id: int) -> None:
        chunks = await self.list_by_bid_notice(bid_notice_id)
        for chunk in chunks:
            await self.session.delete(chunk)
            
    async def get_chunks_by_topics(
        self, 
        bid_notice_id: int, 
        l_topics: Optional[list[str]] = None, 
        s_topics: Optional[list[str]] = None
    ) -> dict:
        """
        특정 공고의 청크 중, 지정된 대분류(l_topic) 또는 소분류(s_topic)를 포함하는 청크를 조회합니다.
        반환 형태: {"개요": {"추진 배경": "원문...", "현황": "원문..."}, "평가기준": {"기본": "원문..."}}
        """
        # 1. 기본 쿼리: 해당 공고의 청크만 필터링
        stmt = select(Chunk).where(Chunk.bid_notice_id == bid_notice_id)
        
        # 2. JSONB 메타데이터 필터 조건 구성
        conditions = []
        if l_topics:
            # metadata->>'l_topic' IN ('개요', '평가기준')
            conditions.append(Chunk.chunk_metadata["l_topic"].astext.in_(l_topics))
            
        if s_topics:
            # metadata->>'s_topic' IN ('추진배경', '현황')
            conditions.append(Chunk.chunk_metadata["s_topic"].astext.in_(s_topics))
            
        # l_topic에 해당하거나 OR s_topic에 해당하는 모든 청크 조회
        if conditions:
            stmt = stmt.where(or_(*conditions))
            
        # 3. DB 쿼리 실행
        result = await self.session.execute(stmt)
        chunks = result.scalars().all()
        
        # 4. LLM이 읽기 편한 사전(Dict) 형태로 데이터 가공
        parsed_data = {}
        
        for chunk in chunks:
            # 메타데이터가 없을 경우 빈 딕셔너리로 처리
            meta = chunk.chunk_metadata or {}
            
            l_topic = meta.get("l_topic", "기타")
            s_topic = meta.get("s_topic", "기본") # s_topic이 없는 경우 '기본'으로 할당
            content = chunk.content or ""
            
            # 대분류 키 초기화
            if l_topic not in parsed_data:
                parsed_data[l_topic] = {}
                
            # 같은 토픽을 가진 청크가 여러 개로 쪼개져 있을 경우, 내용을 이어서 붙임
            if s_topic in parsed_data[l_topic]:
                parsed_data[l_topic][s_topic] += f"\n\n{content}"
            else:
                parsed_data[l_topic][s_topic] = content
                
        return parsed_data
