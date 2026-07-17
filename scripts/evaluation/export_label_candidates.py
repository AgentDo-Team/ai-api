"""Export a pooled multi-notice CSV for human relevance judgments."""

from __future__ import annotations

import argparse
import asyncio
import csv
import json
from datetime import UTC, datetime
from pathlib import Path

from sqlmodel import select

from app.db.models.bid import Chunk
from app.db.session import async_session_factory, engine
from scripts.evaluation.second_filter_benchmark import retrieve_scenario, snapshot_targets
from app.services.second_filter_service import SecondFilterService


async def export(args: argparse.Namespace) -> None:
    notice_ids = [int(value) for value in args.bid_notice_ids.split(",")]
    methods = [value.strip() for value in args.methods.split(",")]
    filters = json.loads(args.filters)
    async with async_session_factory() as session:
        service = SecondFilterService(session)
        targets = await service._load_targets(args.company_id)
        if not targets:
            raise ValueError("company has no embedded profile/project")
        results = {
            method: await retrieve_scenario(service, notice_ids, args.message, method, targets, args.pool_k)
            for method in methods
        }
        pooled_ids = {
            chunk_id
            for result in results.values()
            for ranking in result.values()
            for chunk_id in ranking.chunk_ids
        }
        chunks = list((await session.exec(select(Chunk).where(Chunk.id.in_(pooled_ids)))).all())
        chunk_by_id = {chunk.id: chunk for chunk in chunks}

    rows = []
    filters_json = json.dumps(filters, ensure_ascii=False, separators=(",", ":"))
    for notice_id in notice_ids:
        rank_by_method = {
            method: {chunk_id: rank for rank, chunk_id in enumerate(results[method][notice_id].chunk_ids, 1)}
            for method in methods
        }
        notice_pool = sorted(
            set().union(*(set(ranks) for ranks in rank_by_method.values())),
            key=lambda cid: (min(ranks.get(cid, 10**9) for ranks in rank_by_method.values()), cid),
        )
        for chunk_id in notice_pool:
            chunk = chunk_by_id[chunk_id]
            metadata = chunk.chunk_metadata or {}
            rows.append({
                "case_id": args.case_id,
                "company_id": args.company_id,
                "filters_json": filters_json,
                "bid_notice_id": notice_id,
                "message": args.message or "",
                "notice_relevance": "",
                "chunk_id": chunk_id,
                "l_topic": metadata.get("l_topic", ""),
                "page_no": chunk.page_no or "",
                "content": chunk.content or "",
                "chunk_relevance": "",
                "dense_rank": rank_by_method.get("dense", {}).get(chunk_id, ""),
                "bm25_rank": rank_by_method.get("bm25", {}).get(chunk_id, ""),
                "rrf_rank": rank_by_method.get("rrf", {}).get(chunk_id, ""),
                "retrieved_by": ",".join(method for method, ranks in rank_by_method.items() if chunk_id in ranks),
                "notes": "",
            })

    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("w", encoding="utf-8-sig", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)

    context_output = args.context_output or args.output.with_suffix(".context.json")
    context_output.write_text(
        json.dumps(
            {
                "case_id": args.case_id,
                "company_id": args.company_id,
                "bid_notice_ids": notice_ids,
                "message": args.message,
                "filters": filters,
                "methods": methods,
                "pool_k": args.pool_k,
                "generated_at": datetime.now(UTC).isoformat(),
                "targets": snapshot_targets(targets),
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    print(f"{args.output} ({len(notice_ids)} notices, {len(rows)} pooled chunks)")
    print(context_output)
    await engine.dispose()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--case-id", required=True)
    parser.add_argument("--company-id", type=int, required=True)
    parser.add_argument("--bid-notice-ids", required=True, help="comma-separated IDs")
    parser.add_argument("--message", default=None)
    parser.add_argument("--filters", default="{}", help="JSON kept as scenario metadata")
    parser.add_argument("--methods", default="dense,bm25,rrf")
    parser.add_argument("--pool-k", type=int, default=50)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--context-output", type=Path, default=None)
    return parser.parse_args()


if __name__ == "__main__":
    asyncio.run(export(parse_args()))
