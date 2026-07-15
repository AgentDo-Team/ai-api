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
        """CHUNKED 상태인 공고를 찾아 벡터 임베딩을 수행하고 EMBEDDED 상태로 변경합니다."""
        pipeline_start_time = time.time()
        print("\n🚀 [시스템] 청크 임베딩 파이프라인 작업을 시작...")

        # 1. 임베딩 대기 중인 공고 목록 조회
        notices = await self.bid_repo.get_chunked_notices()
        
        if not notices:
            print("임베딩을 진행할 공고가 없습니다.")
            return

        for notice in notices:
            print(f"\n[임베딩 시작] 공고번호: {notice.notice_no}")
            
            try:
                # 2. 해당 공고의 임베딩 없는(IS NULL) 청크만 조회
                chunks = await self.chunk_repo.get_unembedded_chunks(notice.id)

                if not chunks:
                    print("  -> 임베딩할 청크가 없습니다. 상태를 EMBEDDED로 업데이트합니다.")
                    await self.bid_repo.update_status(notice.id, ParseStatus.EMBEDDED)
                    await self.session.commit()
                    continue

                # 3. 텍스트 추출 및 한 번에(Batch) API 호출
                texts = [c.content for c in chunks]
                print(f"  -> {len(texts)}개 청크 임베딩 생성 중...")

                BATCH_SIZE = 50
                vectors = []

                for i in range(0, len(texts), BATCH_SIZE):
                    batch_texts = texts[i : i + BATCH_SIZE]
                    print(f"     ... {i+1} ~ {min(i+BATCH_SIZE, len(texts))} 번째 청크 요청 중 ...")
                    
                    # OpenAI API 호출
                    batch_vector_data = await embed_texts(batch_texts)
                    
                    # 반환된 [{"dense": [...]}, ...] 형태에서 벡터만 추출하여 누적
                    vectors.extend([v["dense"] for v in batch_vector_data])
                    
                
                # 반환값 형식: [{"dense": [...]}, {"dense": [...]}, ...]
                vector_data_list = await embed_texts(texts)
                
                # 순수한 리스트 형태의 벡터값만 추출: [[...], [...], ...]
                vectors = [v["dense"] for v in vector_data_list]

                # 4. 청크 객체에 임베딩 값 업데이트
                await self.chunk_repo.update_embeddings(chunks, vectors)

                # 5. 공고 상태를 최종 'EMBEDDED'로 변경
                await self.bid_repo.update_status(notice.id, ParseStatus.EMBEDDED)

                # 6. 트랜잭션 커밋 (데이터베이스에 UPDATE 반영)
                await self.session.commit()
                print(f"[성공] '{notice.title}' 임베딩 및 상태 변경 완료")

            except Exception as e:
                # OpenAI API Timeout 등의 에러 발생 시, 
                # 현재 공고에 대한 작업을 롤백하고 다음 공고로 넘어감
                await self.session.rollback()
                print(f"[에러] '{notice.notice_no}' 임베딩 실패 (롤백됨): {e}")

        pipeline_end_time = time.time()
        elapsed_seconds = pipeline_end_time - pipeline_start_time
        minutes, seconds = divmod(elapsed_seconds, 60)
        
        print(f"\n[시스템] 청크 임베딩 파이프라인 작업이 모두 완료!")
        print(f"⏱총 소요 시간: {int(minutes)}분 {seconds:.2f}초")
