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