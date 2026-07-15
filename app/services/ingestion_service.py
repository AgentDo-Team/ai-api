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
        # OpenAI 임베딩 모델(text-embedding-3 시리즈 및 ada-002)에서 사용하는 기본 인코딩
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
                # 1. 마크다운 처리
                processed_md = convert_md_tables_to_html(notice.raw_md_text)
                structure = analyze_toc_with_gpt(processed_md)
                bullets = extract_bullet_hierarchy(processed_md)
                
                # 2. 정밀 청킹
                primary = slice_rfp_by_headers(processed_md, structure)
                merged = merge_tiny_chunks(primary, min_len=50)
                final_chunks = refine_chunks_by_bullets_and_tables(merged, bullets)
                
                # 3. 청크 존재 여부 체크
                if not final_chunks:
                    print(f"[파싱 실패] 생성된 청크가 없습니다. 상태를 ERROR로 변경합니다.")
                    await self.bid_repo.update_status(notice.id, ParseStatus.ERROR)
                    await self.session.commit()
                    continue
                
                # Tiktoken 기반 거대 청크 안전 분할
                MAX_TOKENS = 7500   # OpenAI 제한(8192)을 고려해 안전하게 7500 토큰으로 설정
                OVERLAP_TOKENS = 400 # 문맥 유지를 위해 약 400 토큰(한글 150~200자) 겹치게 설정

                safe_chunks = []
                for c in final_chunks:
                    content = c['content']
                    
                    # 텍스트를 토큰 배열로 변환
                    tokens = self.tokenizer.encode(content)
                    
                    if len(tokens) <= MAX_TOKENS:
                        # 토큰 수가 안전 범위 내면 그대로 추가 (토큰 수도 함께 저장하면 좋습니다)
                        c['token_count'] = len(tokens)
                        safe_chunks.append(c)
                    else:
                        # 제한을 초과하는 거대 청크는 토큰 단위로 슬라이싱
                        start = 0
                        part_num = 1
                        while start < len(tokens):
                            end = start + MAX_TOKENS
                            # 토큰을 잘라서 다시 문자열(텍스트)로 복원 (decode)
                            part_tokens = tokens[start:end]
                            part_content = self.tokenizer.decode(part_tokens)
                            
                            safe_chunks.append({
                                "l_topic": c['l_topic'],
                                "s_topic": f"{c['s_topic']} (Part {part_num})",
                                "content": part_content,
                                "token_count": len(part_tokens)
                            })
                            
                            # 오버랩만큼 뒤로 가서 다음 청크 시작
                            start += (MAX_TOKENS - OVERLAP_TOKENS)
                            part_num += 1

                # 4. 청크 리스트 저장
                chunk_objs = []
                for idx, c in enumerate(safe_chunks):
                    chunk_objs.append(Chunk(
                        bid_notice_id=notice.id,
                        chunk_index=idx,
                        content=c['content'],
                        chunk_metadata={"l_topic": c['l_topic'], "s_topic": c['s_topic']},
                        token_count=c.get('token_count', 0), # 텍스트 길이가 아닌 실제 토큰 수 저장
                        lexical_weights=None,          
                        page_no=None                
                    ))
                
                await self.chunk_repo.add_all(chunk_objs)
                
                # 5. 최종 완료 처리
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