import re
from typing import List


def extract_bullet_hierarchy(raw_text: str) -> List[str]:
    """
    문서 전체를 스캔하여 특수기호 및 숫자/문자 혼합형 단락 기호 추출
    """
    # 탐색할 단락 기호 정규식 패턴 목록
    bullet_patterns = [
        r'□', r'', r'○', r'ㅇ', r'◦', r'▸', r'▶', r'●', r'-', r'ㆍ', r'※',
        r'\d+\.',        # 1., 2. 등
        r'[가-하]\.',    # 가., 나. 등
        r'\d+\)',        # 1), 2) 등
        r'[가-하]\)',    # 가), 나) 등
        r'[①②③④⑤⑥⑦⑧⑨⑩]', # 원문자
        r'\(\d+\)',      # (1), (2) 등
        r'\([가-하]\)'   # (가), (나) 등
    ]
    
    found_bullets = []
    
    for pattern in bullet_patterns:
        # 각 패턴으로 시작하는 첫 번째 문자열 탐색
        match = re.search(rf'^\s*(?:#+\s*)?({pattern})\s+', raw_text, re.MULTILINE)
        if match:
            matched_str = match.group(1)
            # 패턴 정규식이 아닌 실제 매칭된 기호(예: '1.', '가)')를 저장
            if matched_str not in found_bullets:
                found_bullets.append(matched_str)
                
    # 문서에 인식된 기호가 없을 경우 기본값 반환
    return found_bullets if found_bullets else ['□','', '◦', '-']

def merge_tiny_chunks(chunks: list, min_len: int = 50) -> list:
    """
    내용이 너무 짧은 청크(예: '## 가', '## 추진목표')를 
    독립된 청크로 두지 않고 다음 청크의 내용 상단에 병합합니다.
    """
    merged = []
    temp_buffer = []
    
    for chunk in chunks:
        text = chunk["content"].strip()
        
        # 텍스트가 매우 짧고, HTML 테이블이 포함되어 있지 않다면 버퍼에 임시 보관
        if len(text) < min_len and "<table>" not in text:
            temp_buffer.append(text)
        else:
            # 버퍼에 모아둔 짧은 제목들이 있다면 현재 본문 청크 앞부분에 합침
            if temp_buffer:
                text = "\n".join(temp_buffer) + "\n\n" + text
                temp_buffer = [] # 버퍼 비우기
            
            merged.append({
                "l_topic": chunk["l_topic"],
                "s_topic": chunk["s_topic"], # 실질적인 내용이 담긴 청크의 소분류를 따름
                "content": text
            })
            
    # 문서 끝까지 순회했는데 버퍼에 내용이 남은 경우 처리
    if temp_buffer:
        if merged:
            merged[-1]["content"] += "\n\n" + "\n".join(temp_buffer)
            
    return merged