"""Convert completed pooled-label CSVs to evaluation JSONL."""

from __future__ import annotations

import argparse
import csv
import json
from collections import defaultdict
from pathlib import Path


def build_cases(input_paths: list[Path]) -> list[dict]:
    grouped: dict[str, list[dict[str, str]]] = defaultdict(list)
    contexts: dict[str, dict] = {}
    for path in input_paths:
        context_name = path.with_suffix(".context.json").name
        context_candidates = [
            path.with_suffix(".context.json"),
            Path("evaluation/labels") / context_name,
        ]
        if path.stem.endswith("-corrected"):
            original_name = f"{path.stem.removesuffix('-corrected')}.context.json"
            context_candidates.extend(
                [path.with_name(original_name), Path("evaluation/labels") / original_name]
            )
        context_path = next(
            (candidate for candidate in context_candidates if candidate.exists()),
            context_candidates[-1],
        )
        if not context_path.exists():
            raise ValueError(f"missing context snapshot: {context_path}")
        context = json.loads(context_path.read_text(encoding="utf-8"))
        contexts[context["case_id"]] = context
        with path.open(encoding="utf-8-sig", newline="") as file:
            for row in csv.DictReader(file):
                grouped[row["case_id"]].append(row)

    cases = []
    for case_id, rows in grouped.items():
        first = rows[0]
        context = contexts[case_id]
        by_notice: dict[int, list[dict[str, str]]] = defaultdict(list)
        for row in rows:
            by_notice[int(row["bid_notice_id"])].append(row)

        notice_relevance: dict[int, int] = {}
        chunk_relevance: dict[int, dict[int, int]] = {}
        for notice_id, notice_rows in by_notice.items():
            notice_labels = {row["notice_relevance"].strip() for row in notice_rows}
            if "" in notice_labels or len(notice_labels) != 1:
                raise ValueError(f"{case_id}/{notice_id}: notice_relevance must be filled consistently")
            notice_grade = int(next(iter(notice_labels)))
            if not 0 <= notice_grade <= 3:
                raise ValueError(f"{case_id}/{notice_id}: notice_relevance must be 0..3")
            notice_relevance[notice_id] = notice_grade
            labels: dict[int, int] = {}
            for row in notice_rows:
                if not row["chunk_relevance"].strip():
                    raise ValueError(f"{case_id}/{row['chunk_id']}: chunk_relevance is blank")
                grade = int(row["chunk_relevance"])
                if not 0 <= grade <= 3:
                    raise ValueError(f"{case_id}/{row['chunk_id']}: chunk_relevance must be 0..3")
                labels[int(row["chunk_id"])] = grade
            chunk_relevance[notice_id] = labels

        cases.append({
            "case_id": case_id,
            "company_id": int(first["company_id"]),
            "bid_notice_ids": list(by_notice),
            "message": first["message"] or None,
            "filters": json.loads(first["filters_json"] or "{}"),
            "notice_relevance": notice_relevance,
            "chunk_relevance": chunk_relevance,
            "target_snapshot": context["targets"],
            "notes": "pooled human judgments",
        })
    return cases


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", type=Path, nargs="+", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    cases = build_cases(args.input)
    args.output.write_text("".join(json.dumps(case, ensure_ascii=False) + "\n" for case in cases), encoding="utf-8")
    print(f"{args.output} ({len(cases)} cases)")


if __name__ == "__main__":
    main()
