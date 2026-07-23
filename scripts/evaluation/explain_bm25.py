from __future__ import annotations

import argparse
import asyncio
import json
from pathlib import Path
from typing import Any

from sqlalchemy import text

from app.db.session import async_session_factory, engine
from app.services.second_filter_service import DOMAIN_TOPICS
from scripts.evaluation.second_filter_benchmark import load_cases


def _plan_nodes(value: Any) -> list[dict[str, Any]]:
    nodes: list[dict[str, Any]] = []
    if isinstance(value, dict):
        if "Node Type" in value:
            nodes.append(value)
        for child in value.values():
            nodes.extend(_plan_nodes(child))
    elif isinstance(value, list):
        for child in value:
            nodes.extend(_plan_nodes(child))
    return nodes


async def explain(cases_path: Path, output_path: Path, per_notice_limit: int) -> None:
    [case] = load_cases(cases_path)
    if not case.message:
        raise ValueError("the evaluation case must have a message for BM25 EXPLAIN")

    explain_sql = text(
        """
        EXPLAIN (ANALYZE, BUFFERS, VERBOSE, FORMAT JSON)
        SELECT id, bid_notice_id, score FROM (
            SELECT id, bid_notice_id, pdb.score(id) AS score,
                   ROW_NUMBER() OVER (
                       PARTITION BY bid_notice_id ORDER BY pdb.score(id) DESC
                   ) AS rn
            FROM chunks
            WHERE bid_notice_id = ANY(:ids)
              AND content ||| :query_text
              AND metadata->>'l_topic' = ANY(:l_topics)
        ) ranked
        WHERE rn <= :per_notice_limit
        """
    )

    async with async_session_factory() as session:
        indexes = (
            await session.execute(
                text(
                    """
                    SELECT indexname, indexdef
                    FROM pg_indexes
                    WHERE schemaname = current_schema() AND tablename = 'chunks'
                    ORDER BY indexname
                    """
                )
            )
        ).mappings().all()
        extensions = (
            await session.execute(
                text(
                    """
                    SELECT extname, extversion
                    FROM pg_extension
                    WHERE extname IN ('pg_search', 'vector')
                    ORDER BY extname
                    """
                )
            )
        ).mappings().all()
        result = await session.execute(
            explain_sql,
            {
                "ids": case.bid_notice_ids,
                "query_text": case.message,
                "l_topics": DOMAIN_TOPICS,
                "per_notice_limit": per_notice_limit,
            },
        )
        raw_plan = result.scalar_one()

    plan = raw_plan[0] if isinstance(raw_plan, list) else raw_plan
    nodes = _plan_nodes(plan)
    index_names = sorted(
        {
            str(node.get("Index Name") or node.get("Index"))
            for node in nodes
            if node.get("Index Name") or node.get("Index")
        }
    )
    custom_providers = sorted(
        {
            str(node["Custom Plan Provider"])
            for node in nodes
            if node.get("Custom Plan Provider")
        }
    )
    payload = {
        "case_id": case.case_id,
        "query_text": case.message,
        "bid_notice_ids": case.bid_notice_ids,
        "l_topics": DOMAIN_TOPICS,
        "per_notice_limit": per_notice_limit,
        "extensions": [dict(row) for row in extensions],
        "indexes": [dict(row) for row in indexes],
        "plan_summary": {
            "execution_time_ms": plan.get("Execution Time"),
            "planning_time_ms": plan.get("Planning Time"),
            "top_node_type": (plan.get("Plan") or {}).get("Node Type"),
            "node_types": [node.get("Node Type") for node in nodes],
            "index_names": index_names,
            "custom_plan_providers": custom_providers,
            "bm25_index_present": any(
                row["indexname"] == "idx_chunks_bm25" for row in indexes
            ),
            "bm25_index_named_in_plan": "idx_chunks_bm25" in index_names,
            "bm25_custom_scan_used": any(
                node.get("Custom Plan Provider") == "ParadeDB Base Scan"
                and node.get("Index") == "idx_chunks_bm25"
                for node in nodes
            ),
        },
        "explain": raw_plan,
    }
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(json.dumps(payload["plan_summary"], ensure_ascii=False, indent=2))
    print(output_path)
    await engine.dispose()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--cases", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--per-notice-limit", type=int, default=100)
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()
    asyncio.run(explain(args.cases, args.output, args.per_notice_limit))
