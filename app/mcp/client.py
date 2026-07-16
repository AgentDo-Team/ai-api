import json
import ollama
from fastmcp import Client as MCPClient

# Ollama용 툴 스키마 변환기
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

# 실제 에이전트 루프 로직
async def run_agent_loop(mcp_client: MCPClient, user_prompt: str, tool_schemas: list) -> str:
    messages = [
        {
            "role": "system", 
            "content": """당신은 입찰 제안서 자동화 시스템의 메인 에이전트입니다.
반드시 제공된 도구(Tools)를 다음 순서대로 호출하여 임무를 완수하세요.
1. fetch_proposal_context (DB 조회)
2. generate_draft_json (초안 JSON 작성)
3. create_and_save_docx (DOCX 생성 및 DB 저장)
모든 과정이 끝나면 최종 파일 경로를 응답하세요."""
        },
        {"role": "user", "content": user_prompt}
    ]

    for step in range(5): # 최대 5번 루프
        response = ollama.chat(
            model='qwen2.5:14b', 
            messages=messages,
            tools=tool_schemas
        )

        message = response.get('message', {})
        
        if not message.get('tool_calls'):
            # 툴 호출이 없으면 최종 답변으로 간주
            return message.get('content')

        messages.append(message)

        for tool_call in message['tool_calls']:
            func_name = tool_call['function']['name']
            args = tool_call['function']['arguments']
            
            # MCP 서버에 툴 실행 요청
            tool_result = await mcp_client.call_tool(func_name, args)
            
            messages.append({
                "role": "tool",
                "content": str(tool_result),
                "name": func_name
            })
            
    return "에러: 도구 호출 횟수 초과"

# FastAPI 라우터에서 호출할 메인 진입점 함수
async def run_proposal_agent(user_prompt: str) -> str:
    # ⚠️ 중요: FastAPI가 실행되는 최상위 경로(루트) 기준으로 server.py 위치를 지정해야 합니다.
    SERVER_CMD = "python app/server.py"
    
    mcp_client = MCPClient(SERVER_CMD) 
    
    async with mcp_client:
        # 서버에서 툴 목록 가져오기
        mcp_tools = await mcp_client.list_tools()
        tool_schemas = [to_ollama_tool_schema(t) for t in mcp_tools]
        
        # 에이전트 루프 실행 및 최종 답변 반환
        final_answer = await run_agent_loop(mcp_client, user_prompt, tool_schemas)
        
        return final_answer