
"""
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import StrOutputParser

prompt = ChatPromptTemplate.from_messages([
    ("system", "당신은 친절한 IT 강사입니다. 핵심만 간결하게 설명하세요."),
    ("human", "{question}"),
])
chain = prompt | llm | StrOutputParser()

async for chunk in chain.astream({"question": "비동기 프로그래밍이 왜 필요한가요?"}):
    print(chunk, end="", flush=True)  # 이미 문자열이므로 .content가 필요 없습니다
"""