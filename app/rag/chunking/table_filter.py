"""청크 단위 '평가기준표' 판별기.

RFP 문서를 청크 단위로 쪼갠 뒤, 그 중 배점이 명시된 평가기준표에 해당하는 청크를
규칙 기반(정규식)으로 골라낸다. LLM 호출 없이 동작하므로 1단계(table filter)에서
전체 청크를 스캔하는 저비용 사전 필터로 쓴다.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

# ---------------------------------------------------------------------------
# 신호 정의 (regex는 컴파일해서 재사용)
# ---------------------------------------------------------------------------

# Gate A: 평가 어휘 — '이 청크는 평가를 다룬다'
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

# Gate B: 점수 구조 — '점수를 매기는 표/기준이다'
SCORE_KEYWORD = re.compile(r"배점")                 # 가장 강한 단일 신호
POINT_PATTERN = re.compile(r"\d+(?:\.\d+)?\s*점")     # 90점, 4.5 점 등
TOTAL_PATTERN = re.compile(r"(?:합계|소계|총점|총계|총\s*계)\D{0,6}\d")  # 합계: 100점 등
# 등급 스케일: 평가표 안에서만 유효한 신호로 취급한다.
# 일반 산문/법령 목록에서 '우수·보통' 같은 단어가 우연히 나오는 오탐을 막기 위해,
# (1) 표가 있고 (2) 실제 등급 사다리(5단어 중 3종↑) 이거나 'N등급'일 때만 인정.
GRADE_WORDS = re.compile(r"탁월|우수|보통|미흡|저조")
GRADE_LEVEL = re.compile(r"\d\s*등급")

# 배제 신호: 배점 없는 순수 '요구사항 표'
REQ_TABLE_MARKERS = [
    re.compile(r"요구사항\s*총괄표"),
    re.compile(r"요구사항\s*목록표"),
    re.compile(r"고유\s*번호"),
    re.compile(r"\b(?:MPR|PSR|PMR|QUR|SER|DAR|MHR|SFR|PFR|SIR|SUR|COR|TER)\b"),
]

# 표 존재 여부(보조 신호)
HTML_TABLE = re.compile(r"<table[\s>]")
MD_TABLE_ROW = re.compile(r"^\s*\|.*\|\s*$", re.MULTILINE)

# 섹션 제목이 평가표를 강하게 암시하는 경우(가점)
HEADER_HINT = re.compile(
    r"(?m)^#{1,6}.*?(?:평가\s*항목\s*및\s*배점|평가\s*기준|평가\s*배점|제안서?\s*평가|"
    r"기술능력\s*평가|평가\s*방법|세부\s*평가\s*항목|배점\s*기준|평가\s*점수)"
)


@dataclass
class ChunkVerdict:
    """청크 1개에 대한 판정 결과."""
    is_eval_table: bool
    score: int
    gate_a_hits: int                 # 발화한 평가 어휘 '종류' 수
    gate_b: bool                     # 점수 구조 통과 여부
    disqualified: bool               # 요구사항 표로 배제됐는지
    reasons: list[str] = field(default_factory=list)


def _count_vocab_categories(text: str) -> int:
    """서로 다른 평가 어휘가 몇 '종류' 등장했는지(중복 아님)."""
    return sum(1 for pat in EVAL_VOCAB if pat.search(text))


def _has_grade_scale(text: str, has_table: bool) -> bool:
    # 등급 스케일은 '표 안'에 있을 때만 평가표 신호로 인정한다.
    if not has_table:
        return False
    if len(set(GRADE_WORDS.findall(text))) >= 3:   # 실제 등급 사다리
        return True
    if GRADE_LEVEL.search(text):                    # 'N등급'
        return True
    return False


def _looks_like_requirements_table(text: str, has_baejeom: bool) -> bool:
    """배점이 없으면서 요구사항 표 마커가 있으면 요구사항 표로 본다."""
    if has_baejeom:
        return False  # 배점이 있으면 평가표 쪽에 무게
    return any(pat.search(text) for pat in REQ_TABLE_MARKERS)


def classify_chunk(text: str) -> ChunkVerdict:
    """청크 텍스트 하나를 평가표/비평가표로 판정."""
    reasons: list[str] = []

    has_baejeom = bool(SCORE_KEYWORD.search(text))
    point_hits = len(POINT_PATTERN.findall(text))
    has_total = bool(TOTAL_PATTERN.search(text))
    has_table = bool(HTML_TABLE.search(text)) or bool(MD_TABLE_ROW.search(text))
    has_grade = _has_grade_scale(text, has_table)
    header_hint = bool(HEADER_HINT.search(text))
    gate_a_hits = _count_vocab_categories(text)

    # --- 배제: 배점 없는 순수 요구사항 표 ---
    disqualified = _looks_like_requirements_table(text, has_baejeom)
    if disqualified:
        reasons.append("요구사항 표(배점 없음) → 배제")

    # --- Gate A: 평가 어휘가 최소 1종은 있어야 함 ---
    if gate_a_hits:
        reasons.append(f"평가 어휘 {gate_a_hits}종")

    # --- 통과 경로 2가지 ---
    # (A) '표 기반 평가표': 배점이 있고, 실제 표거나 점수 밀도/합계가 충분
    path_table = has_baejeom and (has_table or point_hits >= 4 or has_total)
    # (B) '산문형 평가기준': 표가 없어도 평가 어휘가 촘촘(3종↑)하고 점수 신호가 있음
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

    # --- 연속형 score (RAG 랭킹/디버깅용) ---
    score = 0
    score += gate_a_hits * 2
    score += 4 if has_baejeom else 0
    score += min(point_hits, 4)            # 점 밀도, 최대 4
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
    """파이프라인에 바로 꽂아 쓸 불리언 API."""
    return classify_chunk(text).is_eval_table
