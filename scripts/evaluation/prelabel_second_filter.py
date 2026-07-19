"""Create transparent, review-first draft labels for second-filter chunks.

The draft grade intentionally does not use dense/BM25/RRF ranks. Retrieval ranks
only decide which rows a human should review first, preventing circular labels
that merely reward the current retrieval implementation.
"""

from __future__ import annotations

import argparse
import csv
import html
import json
import re
from dataclasses import dataclass
from pathlib import Path


TAG_RE = re.compile(r"<[^>]+>")
SPACE_RE = re.compile(r"\s+")

# Grade 3 evidence: capabilities that directly describe the company's NLP/RAG
# offering or the concrete successful-project functionality.
DIRECT_TERMS = (
    "자연어처리",
    "자연어 처리",
    "rag",
    "retrieval augmented generation",
    "챗봇",
    "질의응답",
    "질의 응답",
    "생성형 ai",
    "생성 ai",
    "대규모 언어 모델",
    "llm",
    "민원 자동응답",
    "민원 상담",
    "에이전트 오케스트레이션",
    "도메인 특화 에이전트",
)

# Grade 2 evidence: concrete capabilities demonstrated by the profile/project.
PROJECT_TERMS = (
    "통합정보시스템",
    "통합 정보시스템",
    "공공 정보시스템",
    "공공행정",
    "공공 행정",
    "데이터 연계",
    "시스템 연계",
    "통합 대시보드",
    "fastapi",
    "postgresql",
    "pgvector",
    "python",
    "벡터 검색",
    "임베딩",
)

# Grade 1 evidence: generic SI capability. These terms alone are insufficient
# to claim that the notice directly matches the company's successful project.
GENERIC_TERMS = (
    "정보시스템",
    "시스템 구축",
    "시스템 고도화",
    "응용프로그램",
    "데이터베이스",
    "dbms",
    "api",
    "인터페이스",
    "대시보드",
    "웹 서비스",
    "통합검색",
    "데이터 플랫폼",
)


@dataclass(frozen=True)
class DraftLabel:
    grade: int
    confidence: str
    reason: str
    matched_terms: tuple[str, ...]


def normalize_content(value: str) -> str:
    without_tags = TAG_RE.sub(" ", html.unescape(value or ""))
    return SPACE_RE.sub(" ", without_tags).strip().lower()


def _matches(text: str, terms: tuple[str, ...]) -> list[str]:
    return [term for term in terms if term in text]


def draft_label(content: str) -> DraftLabel:
    """Assign a conservative 0..3 draft grade from content evidence only."""
    text = normalize_content(content)
    direct = _matches(text, DIRECT_TERMS)
    project = _matches(text, PROJECT_TERMS)
    generic = _matches(text, GENERIC_TERMS)

    if len(direct) >= 2 or (direct and project):
        grade = 3
        confidence = "high"
        reason = "회사 NLP/RAG 핵심역량과 프로젝트 수행근거가 함께 확인됨"
    elif direct:
        grade = 3
        confidence = "medium"
        reason = "회사 NLP/RAG 핵심역량과 직접 연결되는 표현이 확인됨"
    elif len(project) >= 2:
        grade = 2
        confidence = "high"
        reason = "성공 프로젝트의 기술·기능 근거가 두 가지 이상 확인됨"
    elif project:
        grade = 2
        confidence = "medium"
        reason = "성공 프로젝트와 연결되는 구체 기술·기능이 확인됨"
    elif generic:
        grade = 1
        confidence = "medium" if len(generic) >= 2 else "low"
        reason = "일반적인 SI 수행역량만 부분적으로 관련됨"
    else:
        grade = 0
        confidence = "high" if len(text) >= 80 else "medium"
        reason = "회사 프로필·성공 프로젝트와 직접 연결되는 근거를 찾지 못함"

    matched = tuple(dict.fromkeys([*direct, *project, *generic]))
    return DraftLabel(grade, confidence, reason, matched)


def _rank(value: str | None) -> int | None:
    value = (value or "").strip()
    return int(value) if value else None


def review_priority(row: dict[str, str], label: DraftLabel) -> tuple[str, str]:
    """Prioritize likely positives, uncertain drafts, and top retrieval rows."""
    ranks = [
        rank
        for rank in (
            _rank(row.get("dense_rank")),
            _rank(row.get("bm25_rank")),
            _rank(row.get("rrf_rank")),
        )
        if rank is not None
    ]
    best_rank = min(ranks) if ranks else None
    notice_grade = _rank(row.get("notice_relevance"))

    reasons: list[str] = []
    if label.grade >= 2:
        reasons.append("관련도 2·3 초안")
    if best_rank is not None and best_rank <= 10:
        reasons.append("검색 상위 10")
    if notice_grade == 0 and label.grade >= 2:
        reasons.append("공고·청크 판정 충돌")

    if reasons:
        return "P0", ", ".join(reasons)
    if (
        label.confidence != "high"
        or label.grade == 1
        or (best_rank is not None and best_rank <= 30)
    ):
        return "P1", "자동판정 불확실, 부분 관련 또는 검색 상위 30"
    return "P2", "고신뢰 0점이며 검색 상위권 밖"


def load_notice_labels(case_path: Path) -> dict[tuple[str, int], int]:
    labels: dict[tuple[str, int], int] = {}
    for line in case_path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        case = json.loads(line)
        case_ids = {case["case_id"]}
        if case["case_id"].endswith("-notice-only"):
            case_ids.add(case["case_id"].removesuffix("-notice-only"))
        for notice_id, grade in case["notice_relevance"].items():
            for case_id in case_ids:
                labels[(case_id, int(notice_id))] = int(grade)
    return labels


def prelabel(input_path: Path, case_path: Path, output_path: Path) -> int:
    notice_labels = load_notice_labels(case_path)
    with input_path.open(encoding="utf-8-sig", newline="") as source:
        reader = csv.DictReader(source)
        rows = list(reader)
        fieldnames = list(reader.fieldnames or [])

    extra_fields = [
        "auto_chunk_relevance",
        "auto_confidence",
        "auto_matched_terms",
        "auto_reason",
        "review_priority",
        "review_reason",
        "final_chunk_relevance",
        "reviewer_notes",
    ]
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8-sig", newline="") as target:
        writer = csv.DictWriter(target, fieldnames=[*fieldnames, *extra_fields])
        writer.writeheader()
        for row in rows:
            key = (row["case_id"], int(row["bid_notice_id"]))
            if key in notice_labels:
                row["notice_relevance"] = str(notice_labels[key])
            label = draft_label(row.get("content", ""))
            priority, priority_reason = review_priority(row, label)
            row.update(
                {
                    "auto_chunk_relevance": str(label.grade),
                    "auto_confidence": label.confidence,
                    "auto_matched_terms": " | ".join(label.matched_terms),
                    "auto_reason": label.reason,
                    "review_priority": priority,
                    "review_reason": priority_reason,
                    "final_chunk_relevance": "",
                    "reviewer_notes": "",
                }
            )
            writer.writerow(row)
    return len(rows)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--cases", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()
    count = prelabel(args.input, args.cases, args.output)
    print(f"{args.output} ({count} rows)")
