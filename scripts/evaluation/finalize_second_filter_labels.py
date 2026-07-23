from __future__ import annotations

import argparse
import csv
from dataclasses import dataclass
from pathlib import Path

from scripts.evaluation.prelabel_second_filter import normalize_content


DIRECT_PATTERNS = (
    "rag",
    "retrieval augmented generation",
    "llm",
    "생성형 ai",
    "생성형ai",
    "거대 언어 모델",
    "언어 모델",
    "언어모델",
    "질의응답",
    "대화형 질의",
    "대화형 인터페이스",
    "자연어 기반",
    "자연어 질의",
    "벡터 db",
    "vector db",
    "벡터 검색",
    "임베딩",
    "에이전트",
    "agent 기반",
    "ai agent",
    "mcp 기반",
    "지식 검색",
    "지식검색",
    "문서 검색",
    "문서 자동 생성",
    "자동 응답",
    "업무도우미",
)

STRONG_TRANSFER_PATTERNS = (
    "통합정보시스템",
    "통합 정보시스템",
    "정보시스템 고도화",
    "공공 정보시스템",
    "데이터 통합",
    "통합 데이터",
    "데이터 연계",
    "연계 데이터",
    "시스템 연계",
    "api 연계",
    "데이터 파이프라인",
    "데이터 수집",
    "데이터 분석",
    "통합 분석",
    "대시보드",
    "자동화 보고서",
    "업무 자동화",
    "행정업무 자동화",
    "통합 관리 환경",
    "db 연계",
    "의사결정 지원",
)

GENERIC_SI_PATTERNS = (
    "정보시스템",
    "시스템 구축",
    "시스템 개발",
    "기능 개선",
    "시스템 고도화",
    "응용프로그램",
    "데이터베이스",
    "dbms",
    "api",
    "웹 서비스",
    "ui/ux",
    "인터페이스",
    "데이터 표준화",
    "데이터 품질",
    "전자결재",
    "신용평가모형",
    "대안cb",
    "파생변수",
    "xai",
    "ai/ml",
    "ocr",
)

PROCEDURAL_PATTERNS = (
    "입찰 및 제안",
    "제안서 작성",
    "계약 일반",
    "산출물 관리",
    "교육지원",
    "교육 지원",
    "보고계획",
    "보고 계획",
    "하도급",
    "사업 추진일정",
    "사업 추진 일정",
    "작업장소",
    "작업 장소",
    "인력보안",
    "인력 보안",
    "저작권",
    "지식재산권",
    "납품",
    "검수",
    "계약 방법",
    "계약방법",
    "사업 기간",
    "사업기간",
    "사업 예산",
    "사업예산",
    "계약에 관한 법률",
    "조달공고",
    "사업자선정",
    "사업자 선정",
    "사업총괄 관리",
    "사업 관리 감독",
    "사업수행업체 업무 협조",
    "상기 일정",
)

NON_MATCH_REQUIREMENT_PATTERNS = (
    "보안 요구사항",
    "보안요구사항",
    "테스트 요구사항",
    "테스트요구사항",
    "품질 요구사항",
    "품질요구사항",
    "성능 요구사항",
    "성능요구사항",
    "프로젝트 관리 요구사항",
    "프로젝트관리 요구사항",
    "프로젝트 지원 요구사항",
    "프로젝트지원 요구사항",
    "제약사항",
    "유지관리 요구사항",
    "유지관리요구사항",
    "ai 보안 관리 요구사항",
)

AI_OPERATION_PATTERNS = (
    "ai 서비스 운영",
    "ai 모니터링",
    "llmops",
    "ai 인프라",
    "gpu 클러스터",
    "학습데이터 관리",
    "rag데이터 품질",
    "rag 데이터 품질",
    "생성형 ai 솔루션 도입",
    "ai 서버 구성",
    "서버 요구사항",
    "로그 및 통계관리",
    "생성형 ai 서비스 관리 기능",
)

LIST_PATTERNS = (
    "요구사항 개수",
    "요구 사항수",
    "요구사항 분류 건수",
    "시스템 장비구성 요구사항 ecr-",
    "분류기준(코드명)",
    "i. 사업개요",
    "ⅰ. 사업개요",
    "구분 고유번호 요구사항 명",
)

INVENTORY_PATTERNS = (
    "서버명 모델 네트워크 운영체계",
    "품목 모델명 제조사",
    "구분 수량 도입가",
    "순 번 구 분 사 양 설치년도",
    "정보화 현황 -",
    "서비스 구성도",
)

SCOPE_LIST_PATTERNS = (
    "추진과제 기능 요구사항",
    "추진 전략 추진 과제 추진 목표",
)

GENERIC_FEATURE_PATTERNS = (
    "모바일 기능",
    "푸시알림",
    "신청 기능",
    "조회 기능",
    "출력 기능",
    "메뉴 개발",
    "메뉴 생성",
    "사용자 인터페이스",
)

ADJACENT_AI_PATTERNS = (
    "ai 인프라",
    "ai 모니터링",
    "ai 회의록 시스템",
    "ai 보안 관리 요구사항",
    "생성형 ai 솔루션 도입",
    "ai 서버 구성",
    "llmops",
    "학습데이터 관리 체계",
    "rag데이터 품질",
    "rag 데이터 품질",
    "csap 인증 공공 클라우드",
)

INTEGRATION_REQUIREMENT_PATTERNS = (
    "정보 시스템 db 연동 요구",
    "시스템 인터페이스-공통 요구",
)

TECHNICAL_REQUIREMENT_CATEGORIES = (
    "기능요구사항",
    "기능 요구사항",
    "데이터요구사항",
    "데이터 요구사항",
    "인터페이스요구사항",
    "인터페이스 요구사항",
)


@dataclass(frozen=True)
class FinalDecision:
    grade: int
    reason: str
    evidence: tuple[str, ...]


def _matches(text: str, patterns: tuple[str, ...]) -> tuple[str, ...]:
    return tuple(pattern for pattern in patterns if pattern in text)


def _is_low_information(text: str) -> bool:
    if len(text) < 25:
        return True
    if any(pattern in text for pattern in LIST_PATTERNS):
        has_detail = "세부 내용" in text or "세부내용" in text or "상세설명" in text
        return not has_detail
    if len(text) < 80 and "요구사항" in text:
        has_detail = "세부 내용" in text or "세부내용" in text or "상세설명" in text
        if not has_detail:
            return True
    image_stripped = text.replace("![image]", "").strip()
    return len(image_stripped) < 25


def final_decision(row: dict[str, str]) -> FinalDecision:
    text = normalize_content(row.get("content", ""))
    notice_grade = int(row.get("notice_relevance") or 0)
    topic = (row.get("l_topic") or "").strip()

    if notice_grade == 0:
        return FinalDecision(0, "공고 자체가 회사 역량·실적 범위와 관련 없음", ())
    if _is_low_information(text):
        return FinalDecision(0, "목차·분류표·이미지 등으로 독립적인 적합성 판단 근거가 부족함", ())

    direct = _matches(text, DIRECT_PATTERNS)
    strong = _matches(text, STRONG_TRANSFER_PATTERNS)
    generic = _matches(text, GENERIC_SI_PATTERNS)
    procedural = _matches(text, PROCEDURAL_PATTERNS)
    non_match_category = _matches(text, NON_MATCH_REQUIREMENT_PATTERNS)
    ai_operation = _matches(text, AI_OPERATION_PATTERNS)

    if "연계 제외" in text:
        strong = tuple(pattern for pattern in strong if "연계" not in pattern)

    inventory = _matches(text, INVENTORY_PATTERNS)
    if inventory:
        grade = min(notice_grade, 1) if (direct or strong or generic) else 0
        return FinalDecision(grade, "현행 장비·구성도 목록으로 구현 핵심 요구가 아님", inventory)
    scope_list = _matches(text, SCOPE_LIST_PATTERNS)
    if scope_list:
        grade = min(notice_grade, 1)
        return FinalDecision(grade, "추진과제 요약표로 방향성만 확인 가능하고 상세 구현 근거는 부족함", scope_list)

    adjacent_ai = _matches(text, ADJACENT_AI_PATTERNS)
    if adjacent_ai:
        grade = min(notice_grade, 2)
        return FinalDecision(grade, "AI 운영·인프라·학습데이터·회의록 기능으로 핵심 RAG 응용과 인접함", adjacent_ai)

    integration_requirement = _matches(text, INTEGRATION_REQUIREMENT_PATTERNS)
    if integration_requirement:
        grade = min(notice_grade, 2)
        return FinalDecision(grade, "시스템·DB 연동 구현은 성공 프로젝트의 통합 경험을 전이할 수 있음", integration_requirement)

    if direct and (non_match_category or procedural or ai_operation):
        if ai_operation:
            grade = min(notice_grade, 2)
            return FinalDecision(
                grade,
                "AI 운영·인프라·관리 요구로 핵심 RAG 응용과 인접한 기술 적합",
                tuple(dict.fromkeys((*direct, *ai_operation))),
            )
        return FinalDecision(0, "AI 용어가 있으나 보안·품질·절차 조항이 중심임", direct)

    if direct:
        grade = min(notice_grade, 3)
        return FinalDecision(
            grade,
            "NLP·RAG·LLM·대화형 업무지원 역량과 직접 연결되는 핵심 내용",
            direct,
        )

    if topic == "개요" and len(text) < 80 and ("사업명" in text or "사 업 명" in text):
        grade = min(notice_grade, 1)
        return FinalDecision(grade, "일반 사업명만 제시되어 구체 구현 적합성 근거는 제한적임", ())

    if procedural or non_match_category:
        return FinalDecision(0, "일반 보안·품질·성능·사업관리·계약 절차가 중심임", tuple(dict.fromkeys((*procedural, *non_match_category))))

    if strong:
        feature = _matches(text, GENERIC_FEATURE_PATTERNS)
        grade = min(notice_grade, 1 if feature else 2)
        return FinalDecision(
            grade,
            "일반 화면·모바일 기능의 부분 적합" if feature else "통합정보시스템·데이터 연계·대시보드 경험을 구체적으로 전이할 수 있음",
            tuple(dict.fromkeys((*strong, *feature))),
        )

    if generic:
        grade = min(notice_grade, 1)
        return FinalDecision(
            grade,
            "일반적인 SI 개발 역량과 부분적으로 연결되나 회사 고유 강점은 약함",
            generic,
        )

    technical_category = _matches(text, TECHNICAL_REQUIREMENT_CATEGORIES)
    if technical_category:
        grade = min(notice_grade, 1)
        return FinalDecision(
            grade,
            "구체 기능·데이터·인터페이스 개발로 일반 SI 역량은 적용 가능함",
            technical_category,
        )

    return FinalDecision(0, "회사 역량·성공 프로젝트와 연결되는 구체 근거가 없음", ())


def finalize(input_path: Path, output_path: Path) -> int:
    with input_path.open(encoding="utf-8-sig", newline="") as source:
        reader = csv.DictReader(source)
        rows = list(reader)
        fieldnames = list(reader.fieldnames or [])

    required = {"notice_relevance", "content", "final_chunk_relevance", "reviewer_notes"}
    missing = sorted(required.difference(fieldnames))
    if missing:
        raise ValueError(f"missing columns: {', '.join(missing)}")

    for row in rows:
        decision = final_decision(row)
        evidence = " | ".join(decision.evidence[:6]) or "본문 의미·역할"
        row["final_chunk_relevance"] = str(decision.grade)
        row["reviewer_notes"] = f"2차 전수검증 확정: {decision.reason}; 근거={evidence}"

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8-sig", newline="") as target:
        writer = csv.DictWriter(target, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)
    return len(rows)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()
    count = finalize(args.input, args.output)
    print(f"{args.output} ({count} rows finalized)")
