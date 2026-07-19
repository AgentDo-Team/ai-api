import csv
import json

from scripts.evaluation.prelabel_second_filter import (
    draft_label,
    prelabel,
    review_priority,
)


def test_direct_nlp_requirement_gets_grade_three():
    label = draft_label("RAG 기반 지능형 질의응답과 도메인 특화 에이전트를 구축한다")

    assert label.grade == 3
    assert label.confidence == "high"
    assert "rag" in label.matched_terms


def test_generic_system_test_is_not_marked_as_direct_match():
    label = draft_label("시스템 테스트 계획과 보안 및 성능 시험 결과서를 제출한다")

    assert label.grade <= 1


def test_search_rank_changes_review_priority_not_draft_grade():
    label = draft_label("관련 없는 장비 교체 사양")
    priority, reason = review_priority(
        {
            "dense_rank": "1",
            "bm25_rank": "",
            "rrf_rank": "20",
            "notice_relevance": "0",
        },
        label,
    )

    assert label.grade == 0
    assert priority == "P0"
    assert "검색 상위 10" in reason


def test_prelabel_preserves_blank_human_fields(tmp_path):
    input_path = tmp_path / "input.csv"
    case_path = tmp_path / "cases.jsonl"
    output_path = tmp_path / "output.csv"
    with input_path.open("w", encoding="utf-8-sig", newline="") as file:
        writer = csv.DictWriter(
            file,
            fieldnames=[
                "case_id",
                "bid_notice_id",
                "content",
                "notice_relevance",
                "dense_rank",
                "bm25_rank",
                "rrf_rank",
            ],
        )
        writer.writeheader()
        writer.writerow(
            {
                "case_id": "case-1",
                "bid_notice_id": "10",
                "content": "공공 RAG 질의응답 구축",
                "notice_relevance": "",
                "dense_rank": "2",
                "bm25_rank": "3",
                "rrf_rank": "1",
            }
        )
    case_path.write_text(
        json.dumps(
                {
                    "case_id": "case-1-notice-only",
                    "notice_relevance": {"10": 3},
            },
            ensure_ascii=False,
        )
        + "\n",
        encoding="utf-8",
    )

    assert prelabel(input_path, case_path, output_path) == 1

    with output_path.open(encoding="utf-8-sig", newline="") as file:
        row = next(csv.DictReader(file))
    assert row["notice_relevance"] == "3"
    assert row["auto_chunk_relevance"] == "3"
    assert row["final_chunk_relevance"] == ""
    assert row["reviewer_notes"] == ""
