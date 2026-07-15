from app.schemas.rfp_schema import DocumentStructure
from langchain_openai import ChatOpenAI
from langchain_core.prompts import ChatPromptTemplate

def analyze_toc_with_gpt(raw_text: str) -> DocumentStructure:
    llm = ChatOpenAI(model="gpt-4o-mini", temperature=0)
    structured_llm = llm.with_structured_output(DocumentStructure)

    system_prompt = """
        당신은 제안요청서(RFP) 문서 구조 분석 전문가입니다.
        제공된 텍스트의 '목차(Table of Contents)'를 기반으로 문서의 전체 뼈대를 추출하세요.

        [핵심 지침 - 매우 중요!]
        1. 목차가 아무리 길어도 중간에 멈추지 마세요. 목차의 마지막 항목까지 단 하나도 누락 없이 100% 모두 추출해야 합니다.
        2. 목차 텍스트 중 페이지 번호(예: ... 15)나 점선(......)은 완전히 제거하고 순수 헤더명(기호 포함, 예: '가. 사업 개요')만 exact_header에 담으세요.
        3. l_topic은 반드시 ['개요', '요구사항', '평가기준', '기타'] 중 하나를 선택하세요.
        4. 목차에 사업 개요, 추진 배경/사업 목적, 범위, 추진 내용, 현황 등의 사업 소개 관련 내용이 있으면 l_topic을 개요로 설정하세요.
        5. 제안요청사항, 요구사항 총괄표 및 목록표, 상세 요구 사항, ~ 요구사항 등의 요구사항 관련 내용이 있으면 l_topic을 요구사항으로 설정하세요.
        6. 목차에 제안서 평가, 제안사 평가, 기술 평가, 사업자 선정 방식, 평가점수표 및 기준 등의 평가 관련 내용이 있으면 l_topic을 평가기준으로 설정하세요.
        7. s_topic은 문서의 맥락을 파악하여 '추진 배경', '현황', '기능 요구사항', '제안서 평가' 등 간결하고 대표성 있는 명사형으로 직접 생성하세요. (비슷한 하위 항목은 같은 s_topic으로 묶어주세요.)
        8. 최상위 대분류(Ⅰ, Ⅱ 등)뿐만 아니라, 그 하위의 중분류/소분류(1, 2, 3, 가, 나 등) 목차도 절대 생략하지 말고 모두 개별 헤더로 추출할 것.
        9. ★, ※ 등 특수기호로 시작하는 목차(예: 평가항목, 배점표 등)도 중요한 독립 헤더이므로 반드시 추출할 것.
        10. '평가', '협상', '기타 사항' 등의 목차는 부록이 아니므로 문서 후반부에 있더라도 100% 추출할 것. 오직 '붙임', '별지', '서식'이라는 단어가 직접 포함된 항목만 제외할 것.
        11. 목차 하단의 '붙임', '별지', '서식' 등은 제외하세요.
        """
    
    prompt = ChatPromptTemplate.from_messages([
        ("system", system_prompt),
        ("user", "--- RFP 목차 탐색용 텍스트 (최상단) ---\n{rfp_text}")
    ])

    front_matter = raw_text[:20000]
    result = (prompt | structured_llm).invoke({"rfp_text": front_matter})
    return result
