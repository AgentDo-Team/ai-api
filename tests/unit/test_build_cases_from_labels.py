import csv
import json

import pytest

from scripts.evaluation.build_cases_from_labels import build_cases


FIELDS = [
    "case_id", "company_id", "filters_json", "bid_notice_id", "message",
    "notice_relevance", "chunk_id", "chunk_relevance",
]


def write_labels(path, blank_chunk=False):
    rows = [
        ["case-1", "2", "{}", "10", "AI", "3", "101", "3"],
        ["case-1", "2", "{}", "10", "AI", "3", "102", "0" if not blank_chunk else ""],
        ["case-1", "2", "{}", "20", "AI", "1", "201", "2"],
    ]
    with path.open("w", encoding="utf-8-sig", newline="") as file:
        writer = csv.writer(file)
        writer.writerow(FIELDS)
        writer.writerows(rows)
    path.with_suffix(".context.json").write_text(
        json.dumps(
            {
                "case_id": "case-1",
                "targets": [
                    {
                        "source": "profile",
                        "id": 1,
                        "text": "회사 프로필",
                        "embedding_sha256": "abc",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )


def test_builds_one_multi_notice_case(tmp_path):
    path = tmp_path / "labels.csv"
    write_labels(path)
    [case] = build_cases([path])
    assert case["bid_notice_ids"] == [10, 20]
    assert case["notice_relevance"] == {10: 3, 20: 1}
    assert case["chunk_relevance"][10] == {101: 3, 102: 0}
    assert case["target_snapshot"][0]["text"] == "회사 프로필"


def test_rejects_unlabeled_pool_rows(tmp_path):
    path = tmp_path / "labels.csv"
    write_labels(path, blank_chunk=True)
    with pytest.raises(ValueError, match="chunk_relevance is blank"):
        build_cases([path])


def test_corrected_csv_uses_original_context_name(tmp_path):
    path = tmp_path / "labels-corrected.csv"
    write_labels(path)
    path.with_suffix(".context.json").rename(tmp_path / "labels.context.json")
    [case] = build_cases([path])
    assert case["case_id"] == "case-1"
