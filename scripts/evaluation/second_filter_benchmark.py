"""Evaluate second-filter retrieval over multi-notice search scenarios."""

from __future__ import annotations

import argparse
import asyncio
import csv
import hashlib
import json
import math
import time
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from statistics import mean
from typing import Any, Literal

import tiktoken
from pydantic import BaseModel, Field, model_validator
from sqlmodel import select

from app.db.models.bid import Chunk
from app.db.session import async_session_factory, engine
from scripts.evaluation.retrieval_metrics import (
    ndcg_at_k,
    hit_rate_at_k,
    percentile,
    recall_at_k,
    reciprocal_rank,
)
from app.services.second_filter_service import (
    DOMAIN_TOPICS,
    RRF_K,
    SecondFilterService,
    _Target,
)

Method = Literal["dense", "bm25", "rrf"]
AggregateMethod = Literal["sum_top_k", "max", "sum_top_3", "discounted_sum"]


class TargetSnapshot(BaseModel):
    source: Literal["profile", "project"]
    id: int
    text: str
    embedding_sha256: str


class EvaluationCase(BaseModel):
    """One company/query applied to the notices that passed the hard filter."""

    case_id: str
    company_id: int
    bid_notice_ids: list[int] = Field(min_length=2)
    message: str | None = None
    filters: dict[str, Any] = Field(default_factory=dict)
    notice_relevance: dict[int, int]
    chunk_relevance: dict[int, dict[int, int]]
    target_snapshot: list[TargetSnapshot] = Field(default_factory=list)
    notes: str | None = None

    @model_validator(mode="after")
    def validate_labels(self) -> "EvaluationCase":
        notice_ids = set(self.bid_notice_ids)
        if len(notice_ids) != len(self.bid_notice_ids):
            raise ValueError("bid_notice_ids must not contain duplicates")
        if set(self.notice_relevance) != notice_ids:
            raise ValueError("notice_relevance must label every bid_notice_id")
        if not set(self.chunk_relevance).issubset(notice_ids):
            raise ValueError("chunk_relevance contains a notice outside bid_notice_ids")
        grades = list(self.notice_relevance.values()) + [
            grade for labels in self.chunk_relevance.values() for grade in labels.values()
        ]
        if any(grade < 0 or grade > 3 for grade in grades):
            raise ValueError("relevance grades must be between 0 and 3")
        return self


@dataclass
class Ranking:
    chunk_ids: list[int]
    scores: list[float]


@dataclass
class BenchmarkRow:
    case_id: str
    method: str
    rrf_k: int
    candidate_k: int
    final_k: int
    aggregate_method: str
    notice_count: int
    ranked_notice_ids: list[int]
    notice_scores: dict[int, float]
    candidate_chunk_ids: dict[int, list[int]]
    final_chunk_ids: dict[int, list[int]]
    candidate_scores: dict[int, list[float]]
    chunk_recall_at_10: float | None
    chunk_recall_at_20: float | None
    chunk_recall_at_50: float | None
    chunk_candidate_recall: float | None
    chunk_recall_at_10_rel2: float | None
    chunk_recall_at_10_rel3: float | None
    chunk_recall_at_20_rel3: float | None
    chunk_recall_at_50_rel3: float | None
    chunk_candidate_recall_rel3: float | None
    chunk_hit_rate_at_10_rel3: float | None
    chunk_mrr: float | None
    chunk_mrr_rel3: float | None
    chunk_ndcg_at_10: float | None
    notice_recall_at_5: float
    notice_recall_at_10: float
    notice_mrr: float
    notice_ndcg_at_10: float
    latency_p50_ms: float
    latency_p95_ms: float
    final_token_count: int


def embedding_sha256(embedding: list[float]) -> str:
    serialized = json.dumps(list(embedding), separators=(",", ":"), ensure_ascii=True)
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()


def snapshot_targets(targets: list[_Target]) -> list[dict[str, Any]]:
    return [
        {
            "source": target.source,
            "id": target.id,
            "text": target.text,
            "embedding_sha256": embedding_sha256(target.embedding),
        }
        for target in targets
    ]


def validate_target_snapshot(case: EvaluationCase, targets: list[_Target]) -> None:
    if not case.target_snapshot:
        return
    expected = [target.model_dump() for target in case.target_snapshot]
    actual = snapshot_targets(targets)
    if actual != expected:
        raise ValueError(
            f"{case.case_id}: company profile/project changed after labeling; "
            "regenerate candidates and labels"
        )


def _fuse(
    rankings: list[list[tuple[object, float]]], limit: int, rrf_k: int = RRF_K
) -> Ranking:
    scores: dict[int, float] = {}
    for ranking in rankings:
        for rank, (chunk, _raw_score) in enumerate(ranking):
            scores[chunk.id] = scores.get(chunk.id, 0.0) + 1 / (rrf_k + rank + 1)
    ordered = sorted(scores, key=lambda chunk_id: (-scores[chunk_id], chunk_id))[:limit]
    return Ranking(ordered, [scores[chunk_id] for chunk_id in ordered])


async def retrieve_scenario(
    service: SecondFilterService,
    notice_ids: list[int],
    message: str | None,
    method: Method,
    targets: list[_Target],
    candidate_k: int,
) -> dict[int, Ranking]:
    """Run a retrieval method while preserving production multi-notice batching."""
    fetch = candidate_k * 2
    rrf_k = getattr(service, "rrf_k", RRF_K)
    rankings: dict[int, Ranking] = {}

    if method == "dense":
        for notice_id in notice_ids:
            lists = [
                await service.chunk_repo.dense_search(
                    notice_id, target.embedding, limit=fetch, l_topics=DOMAIN_TOPICS
                )
                for target in targets
            ]
            rankings[notice_id] = _fuse(lists, candidate_k, rrf_k)
        return rankings

    texts = sorted({target.text for target in targets if target.text.strip()})
    if message and message.strip():
        texts.append(message)

    if method == "bm25":
        sparse = {
            text: await service.chunk_repo.sparse_search_multi(
                notice_ids, text, per_notice_limit=fetch, l_topics=DOMAIN_TOPICS
            )
            for text in dict.fromkeys(texts)
        }
        for notice_id in notice_ids:
            rankings[notice_id] = _fuse(
                [by_notice.get(notice_id, []) for by_notice in sparse.values()],
                candidate_k,
                rrf_k,
            )
        return rankings

    sparse = await service._batch_sparse(notice_ids, targets, message, candidate_k)
    for notice_id in notice_ids:
        ranked = await service._rank_chunks(
            notice_id, targets, message, candidate_k, sparse
        )
        rankings[notice_id] = Ranking(
            [item.chunk_id for item in ranked], [item.score for item in ranked]
        )

    return rankings


def rank_notices(
    rankings: dict[int, Ranking],
    final_k: int,
    aggregate_method: AggregateMethod = "sum_top_k",
) -> tuple[list[int], dict[int, float]]:
    """Rank notices without changing the chunk/output contract.

    Alternative aggregation is benchmark-only until it wins on multiple
    independently labelled company scenarios.
    """

    def aggregate(ranking: Ranking) -> float:
        values = ranking.scores[:final_k]
        if not values:
            return 0.0
        if aggregate_method == "max":
            return max(values)
        if aggregate_method == "sum_top_3":
            return sum(values[:3])
        if aggregate_method == "discounted_sum":
            return sum(score / math.log2(rank + 2) for rank, score in enumerate(values))
        if aggregate_method == "sum_top_k":
            return sum(values)
        raise ValueError(f"unknown aggregate method: {aggregate_method}")

    scores = {notice_id: aggregate(ranking) for notice_id, ranking in rankings.items()}
    return sorted(scores, key=lambda notice_id: (-scores[notice_id], notice_id)), scores


def _macro(values: list[float]) -> float | None:
    return mean(values) if values else None


def calculate_metrics(
    case: EvaluationCase,
    rankings: dict[int, Ranking],
    ranked_notice_ids: list[int],
    candidate_k: int,
) -> dict[str, float | None]:
    def chunk_metric(metric, min_relevance: int = 1) -> float | None:
        judged = [
            (notice_id, labels)
            for notice_id, labels in case.chunk_relevance.items()
            if any(grade >= min_relevance for grade in labels.values())
        ]
        return _macro([metric(rankings[nid].chunk_ids, labels) for nid, labels in judged])

    return {
        "chunk_recall_at_10": chunk_metric(lambda ids, rel: recall_at_k(ids, rel, 10))
        if candidate_k >= 10 else None,
        "chunk_recall_at_20": chunk_metric(lambda ids, rel: recall_at_k(ids, rel, 20))
        if candidate_k >= 20 else None,
        "chunk_recall_at_50": chunk_metric(lambda ids, rel: recall_at_k(ids, rel, 50))
        if candidate_k >= 50 else None,
        "chunk_candidate_recall": chunk_metric(
            lambda ids, rel: recall_at_k(ids, rel, candidate_k)
        ),
        "chunk_recall_at_10_rel2": chunk_metric(
            lambda ids, rel: recall_at_k(ids, rel, 10, min_relevance=2), 2
        ) if candidate_k >= 10 else None,
        "chunk_recall_at_10_rel3": chunk_metric(
            lambda ids, rel: recall_at_k(ids, rel, 10, min_relevance=3), 3
        ) if candidate_k >= 10 else None,
        "chunk_recall_at_20_rel3": chunk_metric(
            lambda ids, rel: recall_at_k(ids, rel, 20, min_relevance=3), 3
        ) if candidate_k >= 20 else None,
        "chunk_recall_at_50_rel3": chunk_metric(
            lambda ids, rel: recall_at_k(ids, rel, 50, min_relevance=3), 3
        ) if candidate_k >= 50 else None,
        "chunk_candidate_recall_rel3": chunk_metric(
            lambda ids, rel: recall_at_k(ids, rel, candidate_k, min_relevance=3), 3
        ),
        "chunk_hit_rate_at_10_rel3": chunk_metric(
            lambda ids, rel: hit_rate_at_k(ids, rel, 10, min_relevance=3), 3
        ) if candidate_k >= 10 else None,
        "chunk_mrr": chunk_metric(reciprocal_rank),
        "chunk_mrr_rel3": chunk_metric(
            lambda ids, rel: reciprocal_rank(ids, rel, min_relevance=3), 3
        ),
        "chunk_ndcg_at_10": chunk_metric(lambda ids, rel: ndcg_at_k(ids, rel, 10)),
        "notice_recall_at_5": recall_at_k(ranked_notice_ids, case.notice_relevance, 5),
        "notice_recall_at_10": recall_at_k(ranked_notice_ids, case.notice_relevance, 10),
        "notice_mrr": reciprocal_rank(ranked_notice_ids, case.notice_relevance),
        "notice_ndcg_at_10": ndcg_at_k(ranked_notice_ids, case.notice_relevance, 10),
    }


async def _load_and_validate_chunks(case: EvaluationCase) -> dict[int, Chunk]:
    labeled_ids = {chunk_id for labels in case.chunk_relevance.values() for chunk_id in labels}
    async with async_session_factory() as session:
        chunks = list((await session.exec(select(Chunk).where(Chunk.id.in_(labeled_ids)))).all()) if labeled_ids else []
    by_id = {chunk.id: chunk for chunk in chunks}
    missing = labeled_ids - set(by_id)
    if missing:
        raise ValueError(f"{case.case_id}: missing chunk IDs: {sorted(missing)}")
    for notice_id, labels in case.chunk_relevance.items():
        for chunk_id in labels:
            chunk = by_id[chunk_id]
            topic = (chunk.chunk_metadata or {}).get("l_topic")
            if chunk.bid_notice_id != notice_id or topic not in DOMAIN_TOPICS:
                raise ValueError(f"{case.case_id}: chunk {chunk_id} is outside notice/domain scope")
    return by_id


async def benchmark_case(
    case: EvaluationCase,
    method: Method,
    candidate_k: int,
    final_k: int,
    warmup: int,
    repeat: int,
    rrf_k: int = RRF_K,
    aggregate_method: AggregateMethod = "sum_top_k",
) -> BenchmarkRow:
    labeled_chunks = await _load_and_validate_chunks(case)
    async with async_session_factory() as session:
        service = SecondFilterService(session, rrf_k=rrf_k)
        targets = await service._load_targets(case.company_id)
        if not targets:
            raise ValueError(f"{case.case_id}: company has no embedded profile/project")
        validate_target_snapshot(case, targets)
        for _ in range(warmup):
            await retrieve_scenario(
                service,
                case.bid_notice_ids,
                case.message,
                method,
                targets,
                candidate_k,
            )
        latencies: list[float] = []
        rankings: dict[int, Ranking] = {}
        for _ in range(repeat):
            started = time.perf_counter()
            rankings = await retrieve_scenario(
                service,
                case.bid_notice_ids,
                case.message,
                method,
                targets,
                candidate_k,
            )
            latencies.append((time.perf_counter() - started) * 1000)

        ranked_notice_ids, notice_scores = rank_notices(
            rankings, final_k, aggregate_method
        )
        metrics = calculate_metrics(case, rankings, ranked_notice_ids, candidate_k)

        final_ids = {nid: ranking.chunk_ids[:final_k] for nid, ranking in rankings.items()}
        all_final_ids = {chunk_id for ids in final_ids.values() for chunk_id in ids}
        fetched = list((await session.exec(select(Chunk).where(Chunk.id.in_(all_final_ids)))).all()) if all_final_ids else []
        content_by_id = {**{cid: chunk.content or "" for cid, chunk in labeled_chunks.items()}, **{c.id: c.content or "" for c in fetched}}
        encoder = tiktoken.get_encoding("cl100k_base")
        token_count = sum(len(encoder.encode(content_by_id.get(cid, ""))) for ids in final_ids.values() for cid in ids)

    return BenchmarkRow(
        case_id=case.case_id,
        method=method,
        rrf_k=rrf_k,
        candidate_k=candidate_k,
        final_k=final_k,
        aggregate_method=aggregate_method,
        notice_count=len(case.bid_notice_ids),
        ranked_notice_ids=ranked_notice_ids,
        notice_scores={nid: round(score, 6) for nid, score in notice_scores.items()},
        candidate_chunk_ids={nid: r.chunk_ids for nid, r in rankings.items()},
        final_chunk_ids=final_ids,
        candidate_scores={nid: [round(score, 8) for score in r.scores] for nid, r in rankings.items()},
        latency_p50_ms=round(percentile(latencies, 50), 3),
        latency_p95_ms=round(percentile(latencies, 95), 3),
        final_token_count=token_count,
        **metrics,
    )


def load_cases(path: Path) -> list[EvaluationCase]:
    return [EvaluationCase.model_validate_json(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def write_results(rows: list[BenchmarkRow], output_dir: Path) -> tuple[Path, Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    run_id = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    json_path, csv_path = output_dir / f"{run_id}.json", output_dir / f"{run_id}.csv"
    payload = [asdict(row) for row in rows]
    json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    with csv_path.open("w", encoding="utf-8-sig", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=list(payload[0]))
        writer.writeheader()
        for row in payload:
            writer.writerow({key: json.dumps(value, ensure_ascii=False) if isinstance(value, (list, dict)) else value for key, value in row.items()})
    return json_path, csv_path


async def main_async(args: argparse.Namespace) -> None:
    cases = load_cases(args.cases)
    methods = [method.strip() for method in args.methods.split(",")]
    rows = [
        await benchmark_case(
            case,
            method,
            args.candidate_k,
            args.final_k,
            args.warmup,
            args.repeat,
            args.rrf_k,
            args.aggregate_method,
        )
        for case in cases for method in methods
    ]
    json_path, csv_path = write_results(rows, args.output_dir)
    print(json_path)
    print(csv_path)
    await engine.dispose()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--cases", type=Path, required=True)
    parser.add_argument("--methods", default="dense,bm25,rrf")
    parser.add_argument("--candidate-k", type=int, default=50)
    parser.add_argument("--final-k", type=int, default=10)
    parser.add_argument("--rrf-k", type=int, default=RRF_K)
    parser.add_argument(
        "--aggregate-method",
        choices=("sum_top_k", "max", "sum_top_3", "discounted_sum"),
        default="sum_top_k",
    )
    parser.add_argument("--warmup", type=int, default=2)
    parser.add_argument("--repeat", type=int, default=10)
    parser.add_argument("--output-dir", type=Path, default=Path("evaluation/results"))
    return parser.parse_args()


if __name__ == "__main__":
    asyncio.run(main_async(parse_args()))
