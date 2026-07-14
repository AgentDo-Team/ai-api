from sqlmodel.ext.asyncio.session import AsyncSession
from app.db.models.bid import Chunk, ParseStatus
from app.db.repositories.bid_respository import BidNoticeRepository, ChunkRepository
from app.utils.md_formatter import convert_md_tables_to_html
from app.llm.toc_extractor import analyze_toc_with_gpt
from app.utils.text_utils import extract_bullet_hierarchy
from app.rag.chunking.rfp_chunker import (
    slice_rfp_by_headers, 
    merge_tiny_chunks, 
    refine_chunks_by_bullets_and_tables
)

class IngestionService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.bid_repo = BidNoticeRepository(session)
        self.chunk_repo = ChunkRepository(session)

    async def run_chunking_pipeline(self):
        """PENDING 상태인 공고를 가져와 청크로 쪼개고 DB에 저장합니다."""
        notices = await self.bid_repo.get_pending_notices()
        
        if not notices:
            print(" 처리할 공고가 없습니다.")
            return

        for notice in notices:
            print(f"\n[파싱 시작] 공고번호: {notice.notice_no}")
            
            try:
                # 1. 마크다운 처리 (테이블 변환, 목차 분석, 기호 스캔)
                processed_md = convert_md_tables_to_html(notice.raw_md_text)
                structure = analyze_toc_with_gpt(processed_md)
                bullets = extract_bullet_hierarchy(processed_md)
                
                # 2. 정밀 청킹
                primary = slice_rfp_by_headers(processed_md, structure)
                merged = merge_tiny_chunks(primary, min_len=50)
                final_chunks = refine_chunks_by_bullets_and_tables(merged, bullets)
                
                # 3. 청크 길이 체크 (중요!)
                if not final_chunks:
                    print(f"[파싱 실패] 생성된 청크가 없습니다. 상태를 ERROR로 변경합니다.")
                    await self.bid_repo.update_status(notice.id, ParseStatus.ERROR)
                    await self.session.commit()
                    continue
                
                # 4. 청크 리스트 저장
                chunk_objs = []
                for idx, c in enumerate(final_chunks):
                    chunk_objs.append(Chunk(
                        bid_notice_id=notice.id,
                        chunk_index=idx,
                        content=c['content'],
                        chunk_metadata={"l_topic": c['l_topic'], "s_topic": c['s_topic']}
                    ))
                
                await self.chunk_repo.add_all(chunk_objs)
                
                # 5. 최종 완료 처리
                await self.bid_repo.update_status(notice.id, ParseStatus.CHUNKED)
                await self.session.commit()
                print(f"🎉 [성공] '{notice.title}' 처리 완료 (청크 {len(chunk_objs)}개)")

            except Exception as e:
                await self.session.rollback()
                print(f"❌ [에러] '{notice.notice_no}' 처리 실패: {e}")
                await self.bid_repo.update_status(notice.id, ParseStatus.ERROR)
                await self.session.commit()