import tiktoken
import time
from sqlmodel.ext.asyncio.session import AsyncSession
from app.core.enums import ParseStatus
from app.db.models.bid import Chunk
from app.db.repositories.bid_respository import BidNoticeRepository
from app.db.repositories.chunk_repository import ChunkRepository
from app.utils.md_formatter import convert_md_tables_to_html
from app.llm.toc_extractor import analyze_toc_with_gpt
from app.utils.text_utils import extract_bullet_hierarchy, merge_tiny_chunks
from app.rag.chunking.rfp_chunker import (
    slice_rfp_by_headers, 
    refine_chunks_by_bullets_and_tables
)

class IngestionService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.bid_repo = BidNoticeRepository(session)
        self.chunk_repo = ChunkRepository(session)
        self.tokenizer = tiktoken.get_encoding("cl100k_base")

    async def run_chunking_pipeline(self):
        """PENDING 상태인 공고를 가져와 청크로 쪼개고 DB에 저장합니다."""
        pipeline_start_time = time.time()
        print("\n🚀 [시스템] 청킹 파이프라인 작업을 시작...")

        notices = await self.bid_repo.get_pending_notices()
        
        if not notices:
            print(" 처리할 공고가 없습니다.")
            return

        for notice in notices:
            print(f"\n[파싱 시작] 공고번호: {notice.notice_no}")
            
            try:
                processed_md = convert_md_tables_to_html(notice.raw_md_text)
                structure = analyze_toc_with_gpt(processed_md)
                bullets = extract_bullet_hierarchy(processed_md)
                
                primary = slice_rfp_by_headers(processed_md, structure)
                merged = merge_tiny_chunks(primary, min_len=50)
                final_chunks = refine_chunks_by_bullets_and_tables(merged, bullets)
                
                if not final_chunks:
                    print(f"[파싱 실패] 생성된 청크가 없습니다. 상태를 ERROR로 변경합니다.")
                    await self.bid_repo.update_status(notice.id, ParseStatus.ERROR)
                    await self.session.commit()
                    continue
                
                MAX_TOKENS = 7500  
                OVERLAP_TOKENS = 400 

                safe_chunks = []
                for c in final_chunks:
                    content = c['content']
                    
                    tokens = self.tokenizer.encode(content)
                    
                    if len(tokens) <= MAX_TOKENS:
                        c['token_count'] = len(tokens)
                        safe_chunks.append(c)
                    else:
                        start = 0
                        part_num = 1
                        while start < len(tokens):
                            end = start + MAX_TOKENS
                            part_tokens = tokens[start:end]
                            part_content = self.tokenizer.decode(part_tokens)
                            
                            safe_chunks.append({
                                "l_topic": c['l_topic'],
                                "s_topic": f"{c['s_topic']} (Part {part_num})",
                                "content": part_content,
                                "token_count": len(part_tokens)
                            })
                            
                            start += (MAX_TOKENS - OVERLAP_TOKENS)
                            part_num += 1

                chunk_objs = []
                for idx, c in enumerate(safe_chunks):
                    chunk_objs.append(Chunk(
                        bid_notice_id=notice.id,
                        chunk_index=idx,
                        content=c['content'],
                        chunk_metadata={"l_topic": c['l_topic'], "s_topic": c['s_topic']},
                        token_count=c.get('token_count', 0), 
                        lexical_weights=None,          
                        page_no=None                
                    ))
                
                await self.chunk_repo.add_all(chunk_objs)
                
                await self.bid_repo.update_status(notice.id, ParseStatus.CHUNKED)
                await self.session.commit()
                print(f"[성공] '{notice.title}' 처리 완료 (최종 청크 {len(chunk_objs)}개 생성)")

            except Exception as e:
                await self.session.rollback()
                print(f"[에러] '{notice.notice_no}' 처리 실패: {e}")
                await self.bid_repo.update_status(notice.id, ParseStatus.ERROR)
                await self.session.commit()

        pipeline_end_time = time.time()
        elapsed_seconds = pipeline_end_time - pipeline_start_time
        minutes, seconds = divmod(elapsed_seconds, 60)
        
        print(f"\n[시스템] 청킹 파이프라인 작업이 모두 완료!")
        print(f"⏱총 소요 시간: {int(minutes)}분 {seconds:.2f}초")