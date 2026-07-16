# client.py
import asyncio
import json
import ollama # pip install ollama
from fastmcp import Client as MCPClient

# 툴 스키마 변환 함수 (Ollama가 인식할 수 있는 포맷으로 변경)
def to_ollama_tool_schema(tool) -> dict:
    raw_schema = getattr(tool, "inputSchema", None) or getattr(tool, "input_schema", None)
    return {
        "type": "function",
        "function": {
            "name": tool.name,
            "description": getattr(tool, "description", ""),
            "parameters": raw_schema if raw_schema else {"type": "object", "properties": {}}
        }
    }

async def run_agent_loop(mcp_client: MCPClient, user_prompt: str, tool_schemas: list) -> str:
    # 1. 초기 메시지 세팅 (오케스트레이터의 역할 부여)
    messages = [
        {
            "role": "system", 
            "content": """당신은 입찰 제안서 자동화 시스템의 메인 에이전트입니다.
반드시 제공된 도구(Tools)를 다음 순서대로 호출하여 임무를 완수하세요.
1. fetch_proposal_context (DB에서 정보 가져오기)
2. generate_draft_json (가져온 정보를 바탕으로 제안서 JSON 데이터 만들기)
3. create_and_save_docx (생성된 JSON으로 파일 만들고 DB 저장하기)
순차적으로 도구를 호출하고, 모든 과정이 끝나면 최종 파일 경로를 사용자에게 알려주세요."""
        },
        {"role": "user", "content": user_prompt}
    ]

    print("\n🤖 [Agent] 작업을 시작합니다...")

    # 최대 5번의 툴 호출 루프 (무한 루프 방지)
    for step in range(5):
        # Ollama 호출 (qwen2.5가 Tool Calling에 매우 뛰어남)
        response = ollama.chat(
            model='qwen2.5:14b', # 설치하신 모델명으로 변경하세요
            messages=messages,
            tools=tool_schemas
        )

        message = response.get('message', {})
        
        # 툴 호출(Tool Call)이 있는지 확인
        if not message.get('tool_calls'):
            print(f"\n🏁 [Agent] 최종 답변: {message.get('content')}")
            return message.get('content')

        # LLM의 응답을 대화 기록에 저장
        messages.append(message)

        # LLM이 지시한 툴 실행
        for tool_call in message['tool_calls']:
            func_name = tool_call['function']['name']
            args = tool_call['function']['arguments']
            
            print(f"\n  ⚙️  에이전트 판단: [{func_name}] 도구 호출 중...")
            print(f"  👉 인자값: {args}")
            
            # 서버(MCP)의 실제 파이썬 함수 실행
            tool_result = await mcp_client.call_tool(func_name, args)
            print(f"  ✅ 도구 실행 완료! (결과 길이: {len(str(tool_result))}자)")

            # 결과를 다시 LLM에게 넘겨주기 위해 기록에 추가
            messages.append({
                "role": "tool",
                "content": str(tool_result),
                "name": func_name
            })
            
    return "에러: 도구 호출 횟수 초과"

async def main():
    # 1. MCP 서버를 서브 프로세스로 실행하며 파이프 연결
    mcp_client = MCPClient("python server.py") 
    
    async with mcp_client:
        print(f"🔗 MCP 서버 연결 상태: {mcp_client.is_connected()}")

        # 2. 서버에 등록된 툴 목록 가져와서 스키마 변환
        mcp_tools = await mcp_client.list_tools()
        tool_schemas = [to_ollama_tool_schema(t) for t in mcp_tools]
        
        print("\n--- 사용 가능한 툴 목록 ---")
        for t in tool_schemas:
            print(f"- {t['function']['name']}")
        print("---------------------------\n")

        # 3. 사용자 요청 입력 (훗날 FastAPI에서 받을 payload 부분)
        question = "검색셋 ID 1번과 공고 ID 999번을 사용해서 제안서 초안을 만들고 문서로 저장해줘."
        
        # 4. 에이전트 루프 실행
        await run_agent_loop(mcp_client, question, tool_schemas)

if __name__ == "__main__":
    asyncio.run(main())