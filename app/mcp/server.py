import json
from pathlib import Path
import sys
import traceback

from langchain_core.output_parsers import JsonOutputParser
from langchain_core.prompts import ChatPromptTemplate
from langchain_ollama import ChatOllama

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT))

from docx import Document
import ollama 
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
            notice = await bid_repo.get_by_id(bid_notice_id)
            chunks = await chunk_repo.get_chunks_by_topics(bid_notice_id, '개요', ['추진배경', '현황', '추진 내용'])
            
            context = {
                "search_set_id": search_set_id,
                "bid_notice_id": bid_notice_id,
                "company_profile": {
                    # getattr을 사용하여 만약 값이 None이거나 필드가 없어도 에러가 나지 않도록 방어합니다.
                    # "회사명": getattr(company_profile, "name", "당사"),
                    "target_techs": getattr(company_profile, "target_techs", "정보 없음"),
                    "offered_solutions": getattr(company_profile, "offered_solutions", "정보 없음"),
                    "strengths_diff": getattr(company_profile, "strengths_diff", "정보 없음")
                },
                "company_projects" : [
                    {
                        "title": getattr(p, "title", "정보 없음"), 
                        "client": getattr(p, "client", "정보 없음"),
                        "develop_features": getattr(p, "develop_features", "정보 없음"),
                        "performance" : getattr(p, "performance", "정보 없음")
                        } for p in company_projects
                ],
                "notice": {
                    "title": getattr(notice, "title", "제목 없음"),
                    "demand_org": getattr(notice, "demand_org", "기관 미상"),
                    "procurement_clsfc_nm": getattr(notice, "procurement_clsfc_nm", "")
                },
                "rfp_chuncks": chunks 
            }

            # 4. JSON 문자열로 변환하여 반환 (ensure_ascii=False로 한글 깨짐 방지)
            return json.dumps(context, ensure_ascii=False)
            
        except Exception as e:
            print("========== DB ERROR ==========")
            traceback.print_exc()

            return json.dumps(
                {
                    "error": str(e)
                },
                ensure_ascii=False
            )
    

# ==========================================
# TOOL 2: 제안서 초안 텍스트 생성 (LLM Worker)
# ==========================================
@mcp.tool()
def generate_draft_json(context_str: str) -> str:
    """
    DB Context를 기반으로 ProposalDraftData를 생성한다.
    """

    print("[Server] Proposal Draft 생성")

    context = json.loads(context_str)

    parser = JsonOutputParser(
        pydantic_object=ProposalDraftData
    )

    prompt = ChatPromptTemplate.from_messages(
        [
            (
                "system",
                """
                당신은 공공 SI사업 제안서 작성 전문가입니다.

                반드시 아래 JSON 형식으로만 응답하세요.

                {format_instructions}
                """
                            ),
                            (
                                "human",
                                """
                다음은 회사 정보와 입찰공고 정보입니다.

                {context}

                아래 항목을 작성하세요.

                1. related_projects
                - 회사 최근 프로젝트 중 공고와 가장 관련있는 것만 선택

                2. proposal_advantage
                - 왜 우리 회사가 적합한지

                3. business_summary
                - 공고를 5줄 내외로 요약

                4. proposal_items
                각 항목은

                - current_state
                - requirment
                - proposal
                - expected_effect

                을 포함해야 합니다.
                """
            )
        ]
    )

    model = ChatOllama(
        model="qwen2.5:14b",
        temperature=0
    )

    chain = (
        prompt.partial(
            format_instructions=parser.get_format_instructions()
        )
        | model
        | parser
    )

    draft_data: ProposalDraftData = chain.invoke(
        {
            "context": json.dumps(
                context,
                ensure_ascii=False,
                indent=2
            )
        }
    )

    references = ProposalReference(
        company_profile=[
            context["company_profile"]["target_techs"],
            context["company_profile"]["offered_solutions"],
            context["company_profile"]["strengths_diff"],
        ],
        projects=[],
        bid_chunks=[]
    )

    result = {
        "search_set_id": context["search_set_id"],
        "bid_notice_id": context["bid_notice_id"],
        "draft_data": draft_data.model_dump(),
        "references": references.model_dump()
    }

    return json.dumps(
        result,
        ensure_ascii=False
    )

def replace_placeholder(doc: Document, replace_map: dict):
    """
    Word 문서의 Placeholder를 치환한다.
    (문단 + 표 모두 지원)
    """

    def replace_in_paragraph(paragraph):
        for run in paragraph.runs:
            for key, value in replace_map.items():
                if key in run.text:
                    run.text = run.text.replace(key, value)

    # 일반 문단
    for paragraph in doc.paragraphs:
        replace_in_paragraph(paragraph)

    # 표 안
    for table in doc.tables:
        for row in table.rows:
            for cell in row.cells:
                for paragraph in cell.paragraphs:
                    replace_in_paragraph(paragraph)

# ==========================================
# TOOL 3: 파일 생성 및 DB 저장
# ==========================================
@mcp.tool()
async def create_and_save_docx(
    draft_json_str: str
) -> str:
    """
    초안 JSON을 받아 템플릿 DOCX의 Placeholder를 치환하고
    ProposalDraft DB에 저장한다.
    """

    print("[Server] 💾 DOCX 생성 및 DB 저장")

    # ------------------------------------
    # JSON 파싱
    # ------------------------------------
    try:
        result = json.loads(draft_json_str)

        search_set_id = result["search_set_id"]
        bid_notice_id = result["bid_notice_id"]
        draft_data = result["draft_data"]
        references = result["references"]

    except Exception:
        return json.dumps(
            {"error": "LLM 결과 JSON 파싱 실패"},
            ensure_ascii=False
        )

    # ------------------------------------
    # Placeholder에 들어갈 문자열 생성
    # ------------------------------------

    related_project_text = ""

    for p in draft_data.get("related_projects", []):
        related_project_text += (
            f"프로젝트명 : {p['title']}\n"
            f"고객사 : {p['client']}\n"
            f"분야 : {p['field']}\n"
            f"기술스택 : {p['tech_stack']}\n"
            f"성과 : {p['performance']}\n\n"
        )

    proposal_items = draft_data.get("proposal_items", [])

    current_state = "\n\n".join(
        item["problem"]
        for item in proposal_items
    )

    requirement = "\n\n".join(
        item["evaluation_criteria"]
        for item in proposal_items
    )

    proposal = "\n\n".join(
        item["solution"]
        for item in proposal_items
    )

    expected_effect = "\n\n".join(
        item["differentiation"]
        for item in proposal_items
    )

    reference = (
        f"회사 프로필 : {references['company_profile']}\n"
        f"프로젝트 ID : {references['projects']}\n"
        f"공고 청크 ID : {references['bid_chunks']}"
    )

    replace_map = {
        "{{RELATED_PROJECT}}": related_project_text,
        "{{PROPOSAL_ADVANTAGE}}": draft_data["proposal_advantage"],
        "{{BUSINESS_SUMMARY}}": draft_data["business_summary"],
        "{{CURRENT_STATE}}": current_state,
        "{{REQUIRMENT}}": requirement,
        "{{PROPOSAL}}": proposal,
        "{{EXPECTED_EFFECT}}": expected_effect,
        "{{REFERENCE}}": reference,
    }

    # ------------------------------------
    # 템플릿 열기
    # ------------------------------------

    template_path = Path("templates/proposal_template.docx")

    doc = Document(template_path)

    # Placeholder 치환
    replace_placeholder(doc, replace_map)

    # ------------------------------------
    # 저장
    # ------------------------------------

    save_dir = Path("/Users/kangminju/Desktop/Secure_Proposals")
    save_dir.mkdir(parents=True, exist_ok=True)

    file_path = save_dir / f"Proposal_Draft_{bid_notice_id}.docx"

    doc.save(file_path)

    # ------------------------------------
    # DB 저장
    # ------------------------------------

    async with async_session_factory() as session:

        try:

            repo = ProposalDraftRepository(session)

            proposal = ProposalDraft(
                bid_notice_id=bid_notice_id,
                search_set_id=search_set_id,
                draft_data=draft_data,
                references=references,
                docx_path=str(file_path),
            )

            await repo.add(proposal)

            await session.commit()
        except Exception as e:
            print("========== DB ERROR ==========")

            await session.rollback()

            return json.dumps(
                {
                    "status": "fail",
                    "message": str(e)
                },
                ensure_ascii=False
            )

    return json.dumps(
        {
            "status": "success",
            "docx_path": str(file_path),
            "message": "제안서 생성 완료"
        },
        ensure_ascii=False
    )


if __name__ == "__main__":
    mcp.run()