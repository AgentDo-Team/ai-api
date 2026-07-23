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

        line_no_spaces = clean_line.replace(" ", "")
        
        line_void_parentheses = re.sub(r'\(.*?\)|\[.*?\]|託.*?〕|〈.*?〉', '', clean_line).replace(" ", "")
        
        is_toc_line = bool(re.search(r'\.{2,}|·{2,}|\s+\d+\s*$|\t+\d+\s*$', clean_line))
        
        matched_header = None
        if not is_toc_line:
            for header_dict in header_list:
                clean_target = header_dict["clean_text"]
                
                if clean_target in line_void_parentheses:
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
            
        if content_started:
            current_content.append(original_line)

    save_chunk() 
    return chunks

def refine_chunks_by_bullets_and_tables(chunks: list, bullet_hierarchy: list) -> list:
    STANDARD_BULLET_PATTERNS = [
        (r"[ⅠⅡⅢⅣⅤⅥⅦⅧⅨⅩ]+\.", "로마자"),
        (r"\d{1,2}\.", "숫자"),
        (r"[가-하]\.", "한글"),
        (r"\d{1,2}\)", "반괄호 숫자"),
        (r"[가-하]\)", "반괄호 한글"),
        (r"\(\d{1,2}\)", "양괄호 숫자"),
        (r"\([가-하]\)", "양괄호 한글"),
        (r"[①-⑳]", "원문자"),
        (r"[□■]", "네모"),
        (r"[○●◦ㅇ]", "원")
    ]

    refined_chunks = []

    for chunk in chunks:
        l_topic, s_topic, content = chunk['l_topic'], chunk['s_topic'], chunk['content']
        lines = content.split('\n')

        top_bullet_name, split_bullet_pattern = 'None', None
        for pat, name in STANDARD_BULLET_PATTERNS:
            regex = re.compile(rf"^\s*{pat}")
            if any(regex.search(line) for line in lines if not line.strip().startswith('#')):
                split_bullet_pattern = regex
                top_bullet_name = name
                break

        current_sub_content = []
        table_depth = 0

        def save_sub_chunk(text_lines):
            text = "\n".join(text_lines).strip()
            if text:
                refined_chunks.append({
                    "l_topic": l_topic, "s_topic": s_topic,
                    "content": text, "top_bul": top_bullet_name
                })
            text_lines.clear()

        for line in lines:
            clean_line = line.strip()

            if "<table>" in clean_line:
                if table_depth == 0:
                    save_sub_chunk(current_sub_content)
                table_depth += 1
                current_sub_content.append(line)
                continue
            
            if "</table>" in clean_line:
                current_sub_content.append(line)
                table_depth = max(0, table_depth - 1)
                if table_depth == 0:
                    save_sub_chunk(current_sub_content)
                continue

            if table_depth > 0:
                current_sub_content.append(line)
                continue

            if clean_line.startswith('#'):
                save_sub_chunk(current_sub_content)
                current_sub_content.append(line)
            elif split_bullet_pattern and split_bullet_pattern.search(clean_line):
                save_sub_chunk(current_sub_content)
                current_sub_content.append(line)
            else:
                current_sub_content.append(line)

        save_sub_chunk(current_sub_content)

    return refined_chunks