import re
from typing import List


def extract_bullet_hierarchy(raw_text: str) -> List[str]:

    bullet_patterns = [
        r'□', r'', r'○', r'ㅇ', r'◦', r'▸', r'▶', r'●', r'-', r'ㆍ', r'※',
        r'\d+\.',        
        r'[가-하]\.',    
        r'\d+\)',      
        r'[가-하]\)',   
        r'[①②③④⑤⑥⑦⑧⑨⑩]', 
        r'\(\d+\)',      
        r'\([가-하]\)'   
    ]
    
    found_bullets = []
    
    for pattern in bullet_patterns:
        match = re.search(rf'^\s*(?:#+\s*)?({pattern})\s+', raw_text, re.MULTILINE)
        if match:
            matched_str = match.group(1)
            if matched_str not in found_bullets:
                found_bullets.append(matched_str)
                
    return found_bullets if found_bullets else ['□','', '◦', '-']

def merge_tiny_chunks(chunks: list, min_len: int = 50) -> list:
    
    merged = []
    temp_buffer = []
    
    for chunk in chunks:
        text = chunk["content"].strip()
        
        if len(text) < min_len and "<table>" not in text:
            temp_buffer.append(text)
        else:
            if temp_buffer:
                text = "\n".join(temp_buffer) + "\n\n" + text
                temp_buffer = [] 
            
            merged.append({
                "l_topic": chunk["l_topic"],
                "s_topic": chunk["s_topic"], 
                "content": text
            })
            
    if temp_buffer:
        if merged:
            merged[-1]["content"] += "\n\n" + "\n".join(temp_buffer)
            
    return merged