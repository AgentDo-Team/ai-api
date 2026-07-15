import re


def _split_gfm_row(line: str) -> list[str]:
    """'| a | b |' 한 줄을 셀 리스트로 분리. \| 이스케이프 처리 포함."""
    s = line.strip()
    if s.startswith("|"):
        s = s[1:]
    if s.endswith("|"):
        s = s[:-1]
    cells = re.split(r"(?<!\\)\|", s)
    return [c.strip().replace("\\|", "|") for c in cells]


def _is_separator(line: str) -> bool:
    """GFM 표 구분선(| --- | --- |)인지 판정."""
    s = line.strip()
    return bool(re.fullmatch(r"\|?\s*:?-{2,}:?\s*(\|\s*:?-{2,}:?\s*)*\|?", s))


def convert_md_tables_to_html(md_text: str) -> str:
    """
    마크다운 텍스트에서 표(|---|) 형식만 찾아 HTML <table> 태그로 변환하고,
    나머지 텍스트는 원본 그대로 유지하여 반환합니다.
    """
    lines = md_text.split("\n")
    out = []
    i, n = 0, len(lines)
    
    while i < n:
        line = lines[i]
        
        # 마크다운 표 시작 감지: 현재 줄이 |로 시작 + 다음 줄이 구분선(|---|)
        if line.lstrip().startswith("|") and i + 1 < n and _is_separator(lines[i + 1]):
            header = _split_gfm_row(line)
            i += 2  # 헤더 + 구분선 건너뜀
            
            body = []
            # 표의 내용이 끝날 때(|로 시작하지 않는 줄이 나올 때)까지 수집
            while i < n and lines[i].lstrip().startswith("|"):
                body.append(_split_gfm_row(lines[i]))
                i += 1
                
            # 수집된 데이터를 HTML <table> 구조로 조립
            out.append("<table>")
            out.append("  <tr>" + "".join(f"<th>{c}</th>" for c in header) + "</tr>")
            for row in body:
                out.append("  <tr>" + "".join(f"<td>{c}</td>" for c in row) + "</tr>")
            out.append("</table>")
        else:
            # 표가 아닌 일반 본문/헤더는 그대로 통과
            out.append(line)
            i += 1
            
    return "\n".join(out)