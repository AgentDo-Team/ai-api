"""Convert completed pooled-label CSVs to evaluation JSONL."""

from __future__ import annotations

import argparse
import csv
import json
from collections import defaultdict
from pathlib import Path


def _context_candidates(path: Path) -> list[Path]:
    candidates = [
        path.with_suffix(".context.json"),
        Path("evaluation/labels") / path.with_suffix(".context.json").name,
    ]
    stem = path.stem
    for suffix in ("-corrected", ".final", ".prelabels"):
        if stem.endswith(suffix):
            original_name = f"{stem.removesuffix(suffix)}.context.json"
            candidates.extend(
                [path.with_name(original_name), Path("evaluation/labels") / original_name]
            )
    return candidates


def _dedupe_target_snapshot(targets: list[dict]) -> list[dict]:
    """Mirror production's exact project-text deduplication in label snapshots."""
    seen_project_texts: set[str] = set()
    unique: list[dict] = []
    for target in targets:
        if target.get("source") != "project":
            unique.append(target)
            continue
        text = str(target.get("text", ""))
        if text in seen_project_texts:
            continue
        seen_project_texts.add(text)
        unique.append(target)
    return unique


def _chunk_grade_value(row: dict[str, str]) -> str:
    if "final_chunk_relevance" in row:
        return row["final_chunk_relevance"].strip()
    return row["chunk_relevance"].strip()


def build_cases(input_paths: list[Path]) -> list[dict]:
    grouped: dict[str, list[dict[str, str]]] = defaultdict(list)
    contexts: dict[str, dict] = {}
    for path in input_paths:
        context_candidates = _context_candidates(path)
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
                grade_value = _chunk_grade_value(row)
                if not grade_value:
                    raise ValueError(f"{case_id}/{row['chunk_id']}: chunk_relevance is blank")
                grade = int(grade_value)
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
            "target_snapshot": _dedupe_target_snapshot(context["targets"]),
            "notes": "pooled finalized judgments",
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
