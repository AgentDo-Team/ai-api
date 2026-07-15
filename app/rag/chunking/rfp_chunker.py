import re

from app.schemas.rfp_schema import DocumentStructure

# 헤더별 분리
def slice_rfp_by_headers(raw_text: str, doc_structure: DocumentStructure):
    lines = raw_text.split('\n')
    chunks = []
    
    current_l_topic = "개요"
    current_s_topic = "사업 개요"
    current_content = []

    header_list = []
    for h in doc_structure.headers:
        core_text = re.sub(r'^([가-하a-zA-Z0-9]+[\.\)\]]\s*)', '', h.exact_header)
        core_text = re.sub(r'^#+\s*', '', core_text).replace(" ", "")
        
        if core_text:
            header_list.append({"clean_text": core_text, "info": h})

    in_table = False
    content_started = False 
    
    def save_chunk():
        if current_content and content_started:
            text = "\n".join(current_content).strip()
            if text:
                chunks.append({
                    "l_topic": current_l_topic,
                    "s_topic": current_s_topic,
                    "content": text
                })
        current_content.clear()

    for line in lines:
        original_line = line
        clean_line = re.sub(r'^#+\s*', '', line).strip()
        
        if not clean_line:
            if content_started: current_content.append(original_line)
            continue

        if "<table>" in clean_line:
            in_table = True
            if content_started: current_content.append(original_line)
            continue
        if "</table>" in clean_line:
            if content_started: current_content.append(original_line)
            in_table = False
            continue
        if in_table:
            if content_started: current_content.append(original_line)
            continue

        # 두 가지 버전의 문자열 생성
        line_no_spaces = clean_line.replace(" ", "")
        
        # 매칭 정확도를 위해 본문 줄에서 모든 형태의 괄호와 괄호 안의 내용을 완전히 제거
        line_void_parentheses = re.sub(r'\(.*?\)|\[.*?\]|託.*?〕|〈.*?〉', '', clean_line).replace(" ", "")
        
        # [방어 로직 강화] 점선뿐만 아니라 공백이나 탭 뒤에 번호가 오는 목차 라인 완벽 차단
        # r'\.{2,}|·{2,}' -> 점선 필터링
        # r'\s+\d+\s*$|\t+\d+\s*$' -> 스페이스나 탭 뒤에 숫자로 끝나는 라인 (예: "과업 개요 1")
        is_toc_line = bool(re.search(r'\.{2,}|·{2,}|\s+\d+\s*$|\t+\d+\s*$', clean_line))
        
        matched_header = None
        if not is_toc_line:
            for header_dict in header_list:
                clean_target = header_dict["clean_text"]
                
                # 괄호가 청소된 본문 줄을 기준으로 매칭 및 길이 평가 수행
                if clean_target in line_void_parentheses:
                    # 괄호를 다 떼어냈으므로, 남은 텍스트 길이는 핵심어 길이와 차이가 거의 없어야 함 (앞의 숫자 3. 정도만 남음)
                    # 방어 조건을 +6 정도로 빡빡하게 줄여서 오탐지를 완벽 차단
                    if len(line_void_parentheses) <= len(clean_target) + 6:
                        matched_header = header_dict
                        break
        if not content_started and matched_header:
            if(matched_header in header_list[:2]):
                content_started = True
                current_content.clear() 
            else:
                matched_header = None

        if matched_header and content_started:
            save_chunk() 
            
            header_info = matched_header["info"]
            current_l_topic = header_info.l_topic
            current_s_topic = header_info.s_topic
            
            # 중복 매칭을 막기 위해 리스트에서 소거
            # header_list.remove(matched_header)
            
        if content_started:
            current_content.append(original_line)

    save_chunk() 
    return chunks

# 단락 기호 별 분리
def refine_chunks_by_bullets_and_tables(chunks: list, bullet_hierarchy: list) -> list:
    """
    1차로 헤더별로 잘린 청크들을 입력받아,
    단락 기호(□,  등)와 <table> 태그를 기준으로 2차 분할합니다.
    """
    refined_chunks = []
    
    # 💡 동적 분할 기준 설정: 문서에서 가장 많이 쓰인 최상위 단락 기호 1~2개 추출 (예: '□', '○')
    # 특수기호가 아닌 일반 텍스트(예: 1., 가.)도 이스케이프 처리하여 정규식에 안전하게 사용
    top_bullets = bullet_hierarchy[:2] if len(bullet_hierarchy) >= 2 else bullet_hierarchy
    escaped_bullets = [re.escape(b) for b in top_bullets]
    
    # 정규식 설명: 줄 시작 부분에 공백이나 마크다운(#)이 올 수 있고, 그 뒤에 지정된 단락 기호가 오는 경우 매칭
    bullet_pattern = re.compile(rf"^\s*(?:#+\s*)?({'|'.join(escaped_bullets)})\s+")

    for chunk in chunks:
        l_topic = chunk['l_topic']
        s_topic = chunk['s_topic']
        content = chunk['content']

        lines = content.split('\n')
        current_sub_content = []
        in_table = False

        # 내부 헬퍼 함수: 현재까지 모인 텍스트를 하나의 청크로 저장하고 버퍼를 비움
        def save_sub_chunk(text_lines):
            text = "\n".join(text_lines).strip()
            if text:
                refined_chunks.append({
                    "l_topic": l_topic,
                    "s_topic": s_topic,
                    "content": text
                })
            text_lines.clear()

        for line in lines:
            clean_line = line.strip()

            # ----------------------------------
            # 1. <table> 분리 로직
            # ----------------------------------
            if "<table>" in clean_line:
                # 테이블이 시작되기 전까지 모인 내용을 먼저 저장! (테이블과 섞이지 않게)
                save_sub_chunk(current_sub_content)
                in_table = True
                current_sub_content.append(line)
                continue

            if "</table>" in clean_line:
                current_sub_content.append(line)
                in_table = False
                # 테이블이 끝났으므로 오직 테이블 내용만 담긴 독립 청크로 즉시 저장!
                save_sub_chunk(current_sub_content)
                continue

            if in_table:
                # 테이블 내부 줄이면 기호 상관없이 무조건 테이블 버퍼에 누적
                current_sub_content.append(line)
                continue

            # ----------------------------------
            # 2. 단락 기호 (□,  등) 분리 로직
            # ----------------------------------
            # 만약 현재 줄이 '□' 같은 최상위 기호로 시작한다면?
            if bullet_pattern.search(line):
                # 이전 단락 기호부터 지금까지 모았던 내용을 청크로 저장!
                save_sub_chunk(current_sub_content)
                # 새로운 단락 기호 내용을 담기 시작
                current_sub_content.append(line)
            else:
                # 일반 텍스트나 하위 기호(예: -)는 현재 단락에 계속 누적
                current_sub_content.append(line)

        # for문이 끝난 뒤 버퍼에 남아있는 마지막 내용 저장
        save_sub_chunk(current_sub_content)

    return refined_chunks