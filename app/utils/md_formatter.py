import re


def _split_gfm_row(line: str) -> list[str]:
    s = line.strip()
    if s.startswith("|"):
        s = s[1:]
    if s.endswith("|"):
        s = s[:-1]
    cells = re.split(r"(?<!\\)\|", s)
    return [c.strip().replace("\\|", "|") for c in cells]


def _is_separator(line: str) -> bool:
    s = line.strip()
    return bool(re.fullmatch(r"\|?\s*:?-{2,}:?\s*(\|\s*:?-{2,}:?\s*)*\|?", s))


def convert_md_tables_to_html(md_text: str) -> str:
    
    lines = md_text.split("\n")
    out = []
    i, n = 0, len(lines)
    
    while i < n:
        line = lines[i]
        
        if line.lstrip().startswith("|") and i + 1 < n and _is_separator(lines[i + 1]):
            header = _split_gfm_row(line)
            
            body = []
            while i < n and lines[i].lstrip().startswith("|"):
                body.append(_split_gfm_row(lines[i]))
                i += 1
                
            out.append("<table>")
            out.append("  <tr>" + "".join(f"<th>{c}</th>" for c in header) + "</tr>")
            for row in body:
                out.append("  <tr>" + "".join(f"<td>{c}</td>" for c in row) + "</tr>")
            out.append("</table>")
        else:
            out.append(line)
            i += 1
            
    return "\n".join(out)