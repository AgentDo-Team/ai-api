from sqlmodel.ext import asyncio
import time
from sqlmodel.ext.asyncio.session import AsyncSession
from app.core.enums import ParseStatus
from app.db.repositories.bid_respository import BidNoticeRepository
from app.db.repositories.chunk_repository import ChunkRepository
from app.services.embedding_client import embed_texts  # 임베딩 함수 경로에 맞게 수정

class ChuckEmbeddingService:
    def __init__(self, session: AsyncSession):
        self.session = session
        self.bid_repo = BidNoticeRepository(session)
        self.chunk_repo = ChunkRepository(session)

    async def run_embedding_pipeline(self):
        pipeline_start_time = time.time()
        print("\n🚀 [시스템] 청크 임베딩 파이프라인 작업을 시작...")

        notices = await self.bid_repo.get_chunked_notices()
        
        if not notices:
            print("임베딩을 진행할 공고가 없습니다.")
            return

        for notice in notices:
            print(f"\n[임베딩 시작] 공고번호: {notice.notice_no}")
            
            try:
                chunks = await self.chunk_repo.get_unembedded_chunks(notice.id)

                if not chunks:
                    print("  -> 임베딩할 청크가 없습니다. 상태를 EMBEDDED로 업데이트합니다.")
                    await self.bid_repo.update_status(notice.id, ParseStatus.EMBEDDED)
                    await self.session.commit()
                    continue

                texts = [c.content for c in chunks]
                print(f"  -> {len(texts)}개 청크 임베딩 생성 중...")

                BATCH_SIZE = 50
                vectors = []

                for i in range(0, len(texts), BATCH_SIZE):
                    batch_texts = texts[i : i + BATCH_SIZE]
                    print(f"     ... {i+1} ~ {min(i+BATCH_SIZE, len(texts))} 번째 청크 요청 중 ...")
                    
                    batch_vector_data = await embed_texts(batch_texts)
                    
                    vectors.extend([v["dense"] for v in batch_vector_data])
                    
                
                vector_data_list = await embed_texts(texts)
                vectors = [v["dense"] for v in vector_data_list]
                await self.chunk_repo.update_embeddings(chunks, vectors)

                await self.bid_repo.update_status(notice.id, ParseStatus.EMBEDDED)

                await self.session.commit()
                print(f"[성공] '{notice.title}' 임베딩 및 상태 변경 완료")

            except Exception as e:
                await self.session.rollback()
                print(f"[에러] '{notice.notice_no}' 임베딩 실패 (롤백됨): {e}")

        pipeline_end_time = time.time()
        elapsed_seconds = pipeline_end_time - pipeline_start_time
        minutes, seconds = divmod(elapsed_seconds, 60)
        
        print(f"\n[시스템] 청크 임베딩 파이프라인 작업이 모두 완료!")
        print(f"⏱총 소요 시간: {int(minutes)}분 {seconds:.2f}초")
