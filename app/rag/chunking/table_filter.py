from __future__ import annotations

import re
from dataclasses import dataclass, field

EVAL_VOCAB = [
    re.compile(r"평가\s*항목"),
    re.compile(r"평가\s*요소"),
    re.compile(r"평가\s*부문"),
    re.compile(r"평가\s*기준"),
    re.compile(r"세부\s*평가\s*항목"),
    re.compile(r"정성적?\s*평가|정성평가"),
    re.compile(r"정량적?\s*평가|정량평가"),
    re.compile(r"기술능력\s*평가|기술\s*평가"),
    re.compile(r"가격\s*평가"),
    re.compile(r"협상\s*적격"),
]

SCORE_KEYWORD = re.compile(r"배점")              
POINT_PATTERN = re.compile(r"\d+(?:\.\d+)?\s*점")   
TOTAL_PATTERN = re.compile(r"(?:합계|소계|총점|총계|총\s*계)\D{0,6}\d") 
GRADE_WORDS = re.compile(r"탁월|우수|보통|미흡|저조")
GRADE_LEVEL = re.compile(r"\d\s*등급")

REQ_TABLE_MARKERS = [
    re.compile(r"요구사항\s*총괄표"),
    re.compile(r"요구사항\s*목록표"),
    re.compile(r"고유\s*번호"),
    re.compile(r"\b(?:MPR|PSR|PMR|QUR|SER|DAR|MHR|SFR|PFR|SIR|SUR|COR|TER)\b"),
]

HTML_TABLE = re.compile(r"<table[\s>]")
MD_TABLE_ROW = re.compile(r"^\s*\|.*\|\s*$", re.MULTILINE)

HEADER_HINT = re.compile(
    r"(?m)^#{1,6}.*?(?:평가\s*항목\s*및\s*배점|평가\s*기준|평가\s*배점|제안서?\s*평가|"
    r"기술능력\s*평가|평가\s*방법|세부\s*평가\s*항목|배점\s*기준|평가\s*점수)"
)


@dataclass
class ChunkVerdict:
    """청크 1개에 대한 판정 결과."""
    is_eval_table: bool
    score: int
    gate_a_hits: int                 
    gate_b: bool                    
    disqualified: bool               
    reasons: list[str] = field(default_factory=list)


def _count_vocab_categories(text: str) -> int:
    return sum(1 for pat in EVAL_VOCAB if pat.search(text))


def _has_grade_scale(text: str, has_table: bool) -> bool:
    if not has_table:
        return False
    if len(set(GRADE_WORDS.findall(text))) >= 3:  
        return True
    if GRADE_LEVEL.search(text):                   
        return True
    return False


def _looks_like_requirements_table(text: str, has_baejeom: bool) -> bool:
    if has_baejeom:
        return False  
    return any(pat.search(text) for pat in REQ_TABLE_MARKERS)


def classify_chunk(text: str) -> ChunkVerdict:
    reasons: list[str] = []

    has_baejeom = bool(SCORE_KEYWORD.search(text))
    point_hits = len(POINT_PATTERN.findall(text))
    has_total = bool(TOTAL_PATTERN.search(text))
    has_table = bool(HTML_TABLE.search(text)) or bool(MD_TABLE_ROW.search(text))
    has_grade = _has_grade_scale(text, has_table)
    header_hint = bool(HEADER_HINT.search(text))
    gate_a_hits = _count_vocab_categories(text)

    disqualified = _looks_like_requirements_table(text, has_baejeom)
    if disqualified:
        reasons.append("요구사항 표(배점 없음) → 배제")

    if gate_a_hits:
        reasons.append(f"평가 어휘 {gate_a_hits}종")

    path_table = has_baejeom and (has_table or point_hits >= 4 or has_total)
    path_prose = gate_a_hits >= 3 and (point_hits >= 3 or has_total or has_grade)

    if has_baejeom:
        reasons.append("'배점' 존재")
    if has_table:
        reasons.append("표 존재")
    if point_hits:
        reasons.append(f"'N점' {point_hits}회")
    if has_total:
        reasons.append("합계/총점 신호")
    if has_grade:
        reasons.append("등급 스케일")

    is_eval = (gate_a_hits >= 1) and (path_table or path_prose) and not disqualified

    score = 0
    score += gate_a_hits * 2
    score += 4 if has_baejeom else 0
    score += min(point_hits, 4)            
    score += 2 if has_total else 0
    score += 2 if has_grade else 0
    score += 2 if header_hint else 0
    score += 1 if has_table else 0
    if disqualified:
        score -= 8

    return ChunkVerdict(
        is_eval_table=is_eval,
        score=score,
        gate_a_hits=gate_a_hits,
        gate_b=(path_table or path_prose),
        disqualified=disqualified,
        reasons=reasons,
    )


def is_eval_criteria_table(text: str) -> bool:
    return classify_chunk(text).is_eval_table
