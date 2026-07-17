import json
from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT))

from docx import Document
from mcp.server.fastmcp import FastMCP
from app.db.models.proposal_drafts import ProposalDraft
from app.db.repositories.analysis_repository import AnalysisResultRepository
from app.db.repositories.bid_respository import BidNoticeRepository
from app.db.repositories.chunk_repository import ChunkRepository
from app.db.repositories.company_repository import CompanyProjectRepository, CompanyRepository
from app.db.repositories.proposal_draft_repository import ProposalDraftRepository
from app.db.repositories.search_set_repository import SearchSetRepository
from app.schemas.proposal import ProposalDraftData, ProposalItem, ProposalReference, RelatedProject
from app.db.session import async_session_factory

# MCP 서버 초기화
mcp = FastMCP("ProposalAgentServer")

# ==========================================
# TOOL 1: DB 조회 (Context 수집)
# ==========================================
@mcp.tool()
async def fetch_proposal_context(search_set_id: int, bid_notice_id: int) -> str:
    """[툴1] 검색셋 ID와 공고 ID를 기반으로 DB에서 회사 정보, 공고 정보, 청크(분석결과)를 모두 조회하여 반환합니다."""
    print(f"[Server] 🔍 DB 조회 실행 (search_set_id: {search_set_id}, bid_notice_id: {bid_notice_id})")
    
    # FastAPI의 Depends 대신, 여기서 직접 세션을 열고 닫습니다.
    # async with를 사용하면 블록이 끝날 때 자동으로 session.close()가 호출되어 안전합니다.
    async with async_session_factory() as session:
        
        # 1. 생성한 세션을 Repository에 직접 주입
        bid_repo = BidNoticeRepository(session)
        chunk_repo = ChunkRepository(session)
        search_set_repo = SearchSetRepository(session)
        analysis_repo = AnalysisResultRepository(session)
        company_repo = CompanyRepository(session)
        company_project_repo = CompanyProjectRepository(session)
        
        try:
            # 2. 실제 DB 쿼리 실행 (await 필수)
            search_set = await search_set_repo.get(search_set_id)
            analysis_result = await analysis_repo.get_by_search_set_and_notice(search_set_id, bid_notice_id)
            company_profile = await company_repo.get(search_set.company_id)
            company_projects = await company_project_repo.get_by_company_id(search_set.company_id)
            notice = await bid_repo.get_by_notice_id(bid_notice_id)
            chunks = await chunk_repo.get_chunks_by_topics(bid_notice_id, ['개요', '평가기준'], ['추진배경', '현황', '필요성'])
            
            context = {
                "회사_정보": {
                    # getattr을 사용하여 만약 값이 None이거나 필드가 없어도 에러가 나지 않도록 방어합니다.
                    "회사명": getattr(company_profile, "name", "당사"),
                    "주력_기술": getattr(company_profile, "target_techs", "정보 없음"),
                    "보유_솔루션": getattr(company_profile, "offered_solutions", "정보 없음"),
                    "강점_및_차별점": getattr(company_profile, "strengths_diff", "정보 없음")
                },
                "회사_최근_성공_프로젝트" : [
                    {
                        "프로젝트명": getattr(p, "title", "정보 없음"), 
                        "고객사": getattr(p, "client", "정보 없음"),
                        "개발한_주요_기능": getattr(p, "develop_features", "정보 없음"),
                        "실적_결과" : getattr(p, "performance", "정보 없음")
                        } for p in company_projects
                ],
                "공고_정보": {
                    "공고명": getattr(notice, "title", "제목 없음"),
                    "수요기관": getattr(notice, "demand_org", "기관 미상"),
                    "분류명": getattr(notice, "procurement_clsfc_nm", "")
                },
                "제안요청서_내용": chunks # 청크는 이미 딕셔너리로 가공되었으므로 그대로 넣습니다.
            }
            
           

            # 4. JSON 문자열로 변환하여 반환 (ensure_ascii=False로 한글 깨짐 방지)
            return json.dumps(context, ensure_ascii=False)
            
        except Exception as e:
            print(f"[Server DB Error] {str(e)}")
            return json.dumps({"error": "DB 조회 중 오류가 발생했습니다."}, ensure_ascii=False)
    

# ==========================================
# TOOL 2: 제안서 초안 텍스트 생성 (LLM Worker)
# ==========================================
@mcp.tool()
def generate_draft_json(context_str: str) -> str:
    """[툴2] DB 조회 결과를 바탕으로 제안서 초안을 작성하고, Pydantic 모델에 맞춘 JSON 문자열을 반환합니다."""
    print("[Server] ✍️ 프롬프트 조합 및 초안 데이터 생성 중...")
    
    import ollama # 서버 내부에서도 문서 생성을 위해 로컬 LLM을 호출 (Worker 역할)
    
    # 1. 프롬프트 조합 (요청하신 템플릿 사용)
    system_prompt = "당신은 1000건의 수주 실적을 가진 제안서 작성 전문가입니다. 제공된 컨텍스트를 바탕으로 JSON 형태로만 응답하세요."
    user_prompt = f"""
    아래 컨텍스트를 바탕으로 제안서 초안을 작성하세요.
    컨텍스트: {context_str}
    
    작성 항목:
    1. 관련 분야 사업실적 (관련 프로젝트 추출)
    2. 제안 목적 및 장점
    3. 사업 이해 및 요약
    4. 추가 제안 사항 (문제점, 평가기준, 해결방안, 차별화 등)
    """
    
    # 2. Ollama 호출 (Pydantic 스키마를 강제하는 구조적 출력 - ollama python 라이브러리 최신 기능 또는 json 모드 사용)
    # (테스트를 위해 Ollama 호출 대신 완벽히 파싱된 가상 Pydantic 데이터를 생성합니다)
    mock_data = ProposalDraftData(
        related_projects=[RelatedProject(title="A사업", client="국방부", field="국방", tech_stack="Java", performance="성공")],
        proposal_advantage="최신 RAG 기술 적용으로 검색 속도 10배 향상",
        business_summary="노후 레거시 시스템의 성공적인 클라우드 네이티브 전환",
        proposal_items=[ProposalItem(problem="유지보수 비용 증가", evaluation_criteria="아키텍처 우수성", solution="MSA 도입", differentiation="자동화된 CI/CD")]
    )
    mock_refs = ProposalReference(company_profile=["클라우드", "AI"], projects=[101, 102], bid_chunks=[5, 6, 7])
    
    result = {
        "draft_data": mock_data.model_dump(),
        "references": mock_refs.model_dump()
    }
    return json.dumps(result, ensure_ascii=False)


# ==========================================
# TOOL 3: 파일 생성 및 DB 저장
# ==========================================
@mcp.tool()
async def create_and_save_docx(draft_json_str: str, bid_notice_id: int, search_set_id: int) -> str:
    """[툴3] 완성된 초안 JSON을 받아 로컬에 Word(DOCX) 파일을 생성하고, ProposalDraft DB 테이블에 최종 저장합니다."""
    print("[Server] 💾 워드 파일 생성 및 DB 저장 중...")
    
    # 1. JSON 문자열 파싱 (dict 타입으로 변환)
    try:
        data = json.loads(draft_json_str)
        draft_data = data.get("draft_data", {})
        references = data.get("references", {})
    except json.JSONDecodeError:
        return json.dumps({"error": "LLM이 생성한 JSON 형식이 올바르지 않습니다."}, ensure_ascii=False)
    
    # 2. 샌드박싱된 로컬 폴더 생성
    secure_dir = Path("/Users/kangminju/Desktop/Secure_Proposals") # Mac/Linux라면 "/tmp/Secure_Proposals" 
    secure_dir.mkdir(parents=True, exist_ok=True)
    file_path = secure_dir / f"Proposal_Draft_Bid_{bid_notice_id}.docx"
    
    # 3. DOCX 생성 (요청하신 5단계 제안서 포맷 완벽 반영)
    doc = Document()
    doc.add_heading(f"제안서 초안 (공고 ID: {bid_notice_id})", 0)
    
    # [1. 관련 분야 사업실적]
    doc.add_heading('1. 관련 분야 사업실적', level=1)
    for proj in draft_data.get('related_projects', []):
        doc.add_paragraph(f"- {proj.get('title')} ({proj.get('client')}) / 실적: {proj.get('performance')}")
        
    # [2. 제안 목적 및 장점]
    doc.add_heading('2. 제안 목적 및 장점', level=1)
    doc.add_paragraph(draft_data.get('proposal_advantage', ''))
    
    # [3. 사업 이해 및 주요 요구사항]
    doc.add_heading('3. 사업 이해 및 주요 요구사항', level=1)
    doc.add_paragraph(draft_data.get('business_summary', ''))
    
    # [4. 추가 제안 사항]
    doc.add_heading('4. 추가 제안 사항', level=1)
    for item in draft_data.get('proposal_items', []):
        doc.add_heading(f"요구사항 및 문제점: {item.get('problem')}", level=2)
        doc.add_paragraph(f"▸ 평가기준: {item.get('evaluation_criteria')}")
        doc.add_paragraph(f"▸ 제안내용(해결방안): {item.get('solution')}")
        doc.add_paragraph(f"▸ 기대효과 및 차별화: {item.get('differentiation')}")
        doc.add_paragraph("") # 항목 간 공백 추가

    # [5. 생성 근거 (내부 검토용)]
    doc.add_heading('5. 생성 근거 (내부 검토용)', level=1)
    doc.add_paragraph(f"참조된 자사 키워드: {', '.join(references.get('company_profile', []))}")
    doc.add_paragraph(f"참조된 프로젝트 ID: {references.get('projects', [])}")
    doc.add_paragraph(f"참조된 공고 청크 ID: {references.get('bid_chunks', [])}")

    doc.save(str(file_path))
    
    # 4. DB 저장 로직 (직접 세션 열기)
    async with async_session_factory() as session:
        try:
            proposal_draft_repo = ProposalDraftRepository(session)

            # SQLModel은 JSONB 컬럼에 Python dict를 그대로 넣으면 자동으로 변환해 줍니다.
            new_draft = ProposalDraft(
                bid_notice_id=bid_notice_id,
                search_set_id=search_set_id,
                draft_data=draft_data,  # 문자열(str)이 아닌 딕셔너리(dict) 입력
                references=references,  # 문자열(str)이 아닌 딕셔너리(dict) 입력
                docx_path=str(file_path)
            )
            
            saved_draft = await proposal_draft_repo.add(new_draft)
            await session.commit()
            
        except Exception as e:
            await session.rollback() # 에러 발생 시 롤백
            print(f"[Server DB Error] {str(e)}")
            return json.dumps({"error": f"ProposalDraft DB 저장 중 오류가 발생했습니다: {str(e)}"}, ensure_ascii=False)
    
    return json.dumps({
        "status": "success",
        "message": "제안서 파일 생성 및 DB 저장이 성공적으로 완료되었습니다.",
        "docx_path": new_draft.docx_path
    }, ensure_ascii=False)


if __name__ == "__main__":
    mcp.run()