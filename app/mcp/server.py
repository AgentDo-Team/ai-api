import json
from pathlib import Path

from docx import Document
from mcp.server.fastmcp import FastMCP
from app.schemas.proposal import ProposalDraftData, ProposalItem, ProposalReference, RelatedProject
from tools.proposal import generate_draft

# MCP 서버 초기화
mcp = FastMCP("ProposalAgentServer")

# ==========================================
# TOOL 1: DB 조회 (Context 수집)
# ==========================================
@mcp.tool()
def fetch_proposal_context(search_set_id: int, bid_notice_id: int) -> str:
    """[툴1] 검색셋 ID와 공고 ID를 기반으로 DB에서 회사 정보, 공고 정보, 청크(분석결과)를 모두 조회하여 반환합니다."""
    print(f"[Server] 🔍 DB 조회 실행 (search_set_id: {search_set_id}, bid_notice_id: {bid_notice_id})")
    
    # [설명] 실제 환경에서는 주입받은 Session과 Repository를 사용하여 아래 데이터를 가져옵니다.
    # search_set = repo.get_search_set(search_set_id)
    # company_profile = repo.get_company_profile(search_set.company_id)
    # notice = repo.get_bid_notice(bid_notice_id)
    # chunks = repo.get_chunks_by_topics(bid_notice_id, ['개요', '추진배경', '현황', '평가기준'])
    
    # (테스트용 가상 데이터 반환)
    context = {
        "company_name": "아이티센",
        "company_techs": "AI 에이전트, 클라우드 전환",
        "notice_title": "공공 클라우드 전환 사업",
        "demand_org": "한국정보화진흥원",
        "current_state": "기존 레거시 시스템 노후화 및 유지보수 비용 증가",
        "requirement": "보안 요건을 충족하는 클라우드 네이티브 아키텍처 구성",
        "related_project_ids": [101, 102],
        "chunk_ids": [5, 6, 7]
    }
    return json.dumps(context, ensure_ascii=False)


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
def create_and_save_docx(draft_json_str: str, bid_notice_id: int, search_set_id: int) -> str:
    """[툴3] 완성된 초안 JSON을 받아 로컬에 Word(DOCX) 파일을 생성하고, ProposalDraft DB 테이블에 최종 저장합니다."""
    print("[Server] 💾 워드 파일 생성 및 DB 저장 중...")
    data = json.loads(draft_json_str)
    draft_data = data["draft_data"]
    
    # 1. 샌드박싱된 로컬 폴더 생성
    secure_dir = Path("C:/Secure_Proposals") # Mac/Linux라면 "/tmp/Secure_Proposals" 
    secure_dir.mkdir(parents=True, exist_ok=True)
    file_path = secure_dir / f"Proposal_Draft_Bid_{bid_notice_id}.docx"
    
    # 2. DOCX 생성
    doc = Document()
    doc.add_heading(f"제안서 초안 (공고 ID: {bid_notice_id})", 0)
    doc.add_heading('1. 관련 분야 사업실적', level=1)
    for proj in draft_data['related_projects']:
        doc.add_paragraph(f"- {proj['title']} ({proj['client']})")
        
    doc.add_heading('2. 제안 목적 및 장점', level=1)
    doc.add_paragraph(draft_data['proposal_advantage'])
    
    doc.save(str(file_path))
    
    # 3. DB 저장 로직 (실제로는 session.add(new_draft) 사용)
    # new_draft = ProposalDraft(bid_notice_id=..., search_set_id=..., draft_data=..., docx_path=str(file_path))
    
    return json.dumps({
        "status": "success",
        "message": "파일 생성 및 DB 저장 완료",
        "docx_path": str(file_path)
    }, ensure_ascii=False)


if __name__ == "__main__":
    # stdio 방식으로 실행
    mcp.run(transport='stdio')