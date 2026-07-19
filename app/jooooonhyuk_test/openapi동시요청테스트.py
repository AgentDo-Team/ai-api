from langchain_openai import ChatOpenAI
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import StrOutputParser
import asyncio

my_template = ChatPromptTemplate.from_messages([
    ("system", "너는 프로그래밍 초보자를 가르치는 친절한 AI 튜터야."),
    ("human", "{topic}에 대해 5줄 이내로 쉽게 설명해줘. 어려운 용어는 쉬운 말로 풀어줘.")
])

parser = StrOutputParser()

gpt_model = ChatOpenAI(
    model="gpt-4o-mini",
    temperature=0.3,
)

my_gpt_chain = my_template | gpt_model | parser

topics = ["사과", "재귀함수", "포인터", "API", "데이터베이스",
          "알고리즘", "클래스", "람다", "비동기", "캐싱"]

async def openapi_batch():
    print("메소드 호출")
    # 10개 토픽을 동시에 병렬 요청
    inputs = [{"topic": t} for t in topics]
    results = await my_gpt_chain.abatch(
        inputs,
        config={"max_concurrency": 10}  # 동시 실행 개수 제한
    )
    for topic, result in zip(topics, results):
        print(f"\n=== {topic} ===")
        print(result)

if __name__ == "__main__":
    asyncio.run(openapi_batch())