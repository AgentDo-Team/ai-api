import csv

import pytest

from scripts.evaluation.export_label_candidates import load_existing_labels


def write_csv(path, notice_values=("3", "3")):
    with path.open("w", encoding="utf-8-sig", newline="") as file:
        writer = csv.DictWriter(
            file,
            fieldnames=[
                "bid_notice_id",
                "notice_relevance",
                "chunk_id",
                "chunk_relevance",
                "notes",
            ],
        )
        writer.writeheader()
        writer.writerow(
            {
                "bid_notice_id": 10,
                "notice_relevance": notice_values[0],
                "chunk_id": 101,
                "chunk_relevance": 2,
                "notes": "핵심",
            }
        )
        writer.writerow(
            {
                "bid_notice_id": 10,
                "notice_relevance": notice_values[1],
                "chunk_id": 102,
                "chunk_relevance": 0,
                "notes": "",
            }
        )


def test_load_existing_labels(tmp_path):
    path = tmp_path / "labels.csv"
    write_csv(path)
    notice_labels, chunk_labels = load_existing_labels(path)
    assert notice_labels == {10: "3"}
    assert chunk_labels[(10, 101)] == ("2", "핵심")
    assert chunk_labels[(10, 102)] == ("0", "")


def test_rejects_inconsistent_notice_labels(tmp_path):
    path = tmp_path / "labels.csv"
    write_csv(path, ("3", "1"))
    with pytest.raises(ValueError, match="inconsistent notice_relevance"):
        load_existing_labels(path)
