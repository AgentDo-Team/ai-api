import json
from pathlib import Path
from docx import Document
from langchain_core.messages import SystemMessage, HumanMessage, ToolMessage
from langchain_core.output_parsers import JsonOutputParser
from langchain_ollama import ChatOllama
from sqlalchemy.ext.asyncio import AsyncSession
import time
from app.db.models.analysis import AnalysisResult
from app.db.models.proposal_drafts import ProposalDraft
from app.db.repositories.analysis_repository import AnalysisResultRepository
from app.db.repositories.proposal_draft_repository import ProposalDraftRepository
from app.schemas.proposal import ProposalDraftData

# 분리한 Tool 임포트
from app.tools.proposal_tools import get_company_profile, get_company_projects, get_bid_notice

class ProposalService:

    def __init__(self, session: AsyncSession):
        self.session = session
        self.analysis_repo = AnalysisResultRepository(session)
        self.repo = ProposalDraftRepository(session)
        self.template_path = Path("app/templates/proposal_template.docx") # 실제 템플릿 경로로 수정
        self.save_dir = Path("/Users/kangminju/Desktop/Secure_Proposals")

    async def generate_proposal(self, analysis_result_id: int):
        analysis_result = await self.analysis_repo.get(analysis_result_id)
        if not analysis_result:
            raise ValueError(f"AnalysisResult {analysis_result_id} not found.")

        result = await self.generate_draft(analysis_result)
        return result

    async def generate_draft(self, analysis_result: AnalysisResult):
        analysis_dict = {
            column.name: getattr(analysis_result, column.name)
            for column in analysis_result.__table__.columns
        }
        analysis_json_str = json.dumps(
            analysis_dict, 
            ensure_ascii=False, 
            indent=2, 
            default=str
        )

        tools = [get_company_profile, get_company_projects, get_bid_notice]
        
        llm = ChatOllama(model="qwen3:8b", temperature=0).bind_tools(tools)

        parser = JsonOutputParser(
            pydantic_object=ProposalDraftData
        )

        format_instructions = parser.get_format_instructions()

        system_prompt = f"""당신은 공공 SI 제안서 전문가입니다.
            현재 분석 결과는 아래와 같습니다.
            이미 제공된 분석 결과를 최대한 활용해야 하며 불필요한 Tool 호출은 하지 않습니다.
            - search_set_id: {analysis_result.search_set_id}
            - bid_notice_id: {analysis_result.bid_notice_id}
            - 분석 결과: {analysis_json_str}
            필요한 정보가 모두 수집되면 즉시 ProposalDraftData JSON을 생성하세요.
            필요한 정보가 부족하면 적절한 Tool을 호출하고, 같은 Tool을 두 번 이상 호출하지 않습니다.
            충분한 정보가 모이면 최종 응답은 반드시 아래 JSON 형식을 따라야 합니다.
            {format_instructions}
            """
        
        messages = [
            SystemMessage(content=system_prompt),
            HumanMessage(
                content="제안서 초안 작성을 위한 JSON 데이터를 생성해주세요.")
        ]
        
        # Tool 이름으로 빠르게 찾기 위한 Map (루프 밖에서 한 번만 생성)
        tool_map = {
            tool.name: tool
            for tool in tools
        }

        max_iterations = 2
        final_response = None

        for i in range(max_iterations):
            print(f"===== Iteration {i+1} =====")

            # 1. LLM 호출
            start = time.time()
            response = await llm.ainvoke(messages)
            print(f"LLM 응답 시간: {time.time() - start:.2f}초")

            print(f"LLM tool_calls: {response.tool_calls}")
            print(f"LLM 응답 내용: {response.content}")

            # 2. LLM 응답 저장
            messages.append(response)

            # 3. Tool 호출이 없으면 종료
            if not response.tool_calls:
                final_response = response
                break

            # 4. Tool 실행
            for tool_call in response.tool_calls:

                tool_name = tool_call["name"]
                tool_args = tool_call["args"]
                tool_id = tool_call["id"]

                # Tool 이름으로 찾기
                selected_tool = tool_map.get(tool_name)

                if selected_tool is None:
                    messages.append(
                        ToolMessage(
                            content=f"Tool '{tool_name}' not found.",
                            tool_call_id=tool_id,
                        )
                    )
                    continue

                try:
                    start = time.time()
                    tool_result = await selected_tool.ainvoke(tool_args)
                    print(f"{tool_name} 실행시간: {time.time() - start:.2f}초")

                    messages.append(
                        ToolMessage(
                            content=json.dumps(
                                tool_result,
                                ensure_ascii=False
                            ),
                            tool_call_id=tool_id,
                        )
                    )

                except Exception as e:
                    messages.append(
                        ToolMessage(
                            content=f"Tool Error: {str(e)}",
                            tool_call_id=tool_id,
                        )
                    )

        try:
            if final_response:
                parsed_data = parser.invoke(final_response.content)
                return parsed_data
            else:
                return {"error": "최대 반복 횟수 초과로 결과를 생성하지 못했습니다."}
        except Exception as e:
            print(f"JSON Parsing Error: {e}")
            return {"error": "제안서 초안 JSON 파싱 실패", "raw_content": final_response.content if final_response else None}
        
    def _replace_placeholder(self, doc: Document, replace_map: dict):
        """DOCX 내부의 문단과 표에서 Placeholder를 찾아 실제 데이터로 치환하는 헬퍼 함수"""
        # 1. 일반 문단 치환
        for p in doc.paragraphs:
            for key, value in replace_map.items():
                if key in p.text:
                    p.text = p.text.replace(key, str(value))
        
        # 2. 표 내부 치환
        for table in doc.tables:
            for row in table.rows:
                for cell in row.cells:
                    for p in cell.paragraphs:
                        for key, value in replace_map.items():
                            if key in p.text:
                                p.text = p.text.replace(key, str(value))

    async def save_docx(self, bid_notice_id: int, draft_data: dict) -> str:
        """
        1. LLM이 생성한 JSON 데이터를 포맷팅하여 
        2. DOCX 템플릿에 치환하고 
        3. 로컬 파일로 저장한 뒤 파일 경로를 반환합니다.
        """
        self.save_dir.mkdir(parents=True, exist_ok=True)
        
        # --- 데이터 포맷팅 ---
        # 1. 관련 프로젝트 포맷팅
        related_project_text = ""
        for p in draft_data.get("related_projects", []):
            related_project_text += (
                f"▪ 프로젝트명 : {p.get('title', '')}\n"
                f"▪ 고객사 : {p.get('client', '')}\n"
                f"▪ 기술스택 : {p.get('tech_stack', '')}\n"
                f"▪ 실적결과 : {p.get('performance', '')}\n\n"
            )


        # 2. 제안 항목(proposal_items) 포맷팅
        proposal_items = draft_data.get("proposal_items", [])
        current_state = "\n".join(f"- {item.get('current_state', '')}" for item in proposal_items)
        problem = "\n".join(f"- {item.get('problem', '')}" for item in proposal_items)
        proposal = "\n".join(f"- {item.get('proposal', '')}" for item in proposal_items)
        expected_effect = "\n".join(f"- {item.get('expected_effect', '')}" for item in proposal_items)

        # 3. 매핑 딕셔너리 생성 (템플릿의 변수명과 일치해야 함)
        replace_map = {
            "{{RELATED_PROJECT}}": related_project_text.strip(),
            "{{PROPOSAL_ADVANTAGE}}": draft_data.get("proposal_advantage", ""),
            "{{BUSINESS_SUMMARY}}": draft_data.get("business_summary", ""),
            "{{CURRENT_STATE}}": current_state,
            "{{PROBLEM}}": problem,
            "{{PROPOSAL}}": proposal,
            "{{EXPECTED_EFFECT}}": expected_effect,
            "{{REFERENCE}}": "자동 생성됨 (DB 참조)"
        }

        # --- DOCX 생성 및 저장 ---
        doc = Document(self.template_path)
        self._replace_placeholder(doc, replace_map)

        file_name = f"Proposal_Draft_Bid_{bid_notice_id}.docx"
        file_path = self.save_dir / file_name
        doc.save(file_path)

        print(f"[Success] DOCX 저장 완료: {file_path}")
        return str(file_path)

    async def save_result(self, search_set_id: int, bid_notice_id: int, draft_data: dict, docx_path: str):
        """
        생성된 제안서 초안 데이터와 파일 경로를 DB에 저장합니다.
        """
        try:
            proposal_draft = ProposalDraft(
                search_set_id=search_set_id,
                bid_notice_id=bid_notice_id,
                draft_data=draft_data, # JSONB 필드
                docx_path=docx_path
            )
            
            await self.repo.add(proposal_draft)
            await self.session.commit()
            print(f"[Success] DB 저장 완료: search_set_id={search_set_id}, bid_notice_id={bid_notice_id}")
            
            return proposal_draft
            
        except Exception as e:
            await self.session.rollback()
            print(f"[Error] DB 저장 실패: {e}")
            raise e
