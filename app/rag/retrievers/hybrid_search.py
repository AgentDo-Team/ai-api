"""bid_notice의 chunks에 대한 dense+sparse 하이브리드 검색.

dense: pgvector cosine 유사도 (Chunk.embedding)
sparse: pg_search(ParadeDB) BM25 인덱스(idx_chunks_bm25, 한국어 형태소 분석기)
두 순위 리스트를 RRF(Reciprocal Rank Fusion)로 합산한다. 점수 스케일이 서로 다른
dense distance 와 BM25 score 를 정규화 없이 결합하기 위해 순위만 사용한다.
"""

from __future__ import annotations

from dataclasses import dataclass

from app.db.models.bid import Chunk
from app.db.repositories.chunk_repository import ChunkRepository
from app.db.repositories.eval_criteria_reference_repository import EvalCriteriaReferenceRepository
from app.db.seed_eval_criteria_references import ensure_seeded
from app.llm.base import LLMProvider

RRF_K = 60


@dataclass
class ChunkSearchResult:
    chunk: Chunk
    fused_score: float


async def hybrid_search_chunks(
    chunk_repo: ChunkRepository,
    llm: LLMProvider,
    bid_notice_id: int,
    query_text: str,
    limit: int = 5,
) -> list[ChunkSearchResult]:
    query_embedding = await llm.embed(query_text)

    dense_results = await chunk_repo.dense_search(bid_notice_id, query_embedding, limit=limit * 2)
    sparse_results = await chunk_repo.sparse_search(bid_notice_id, query_text, limit=limit * 2)

    fused_scores: dict[int, float] = {}
    chunks_by_id: dict[int, Chunk] = {}

    for rank, (chunk, _distance) in enumerate(dense_results):
        chunks_by_id[chunk.id] = chunk
        fused_scores[chunk.id] = fused_scores.get(chunk.id, 0.0) + 1.0 / (RRF_K + rank + 1)

    for rank, (chunk, _rank_score) in enumerate(sparse_results):
        chunks_by_id[chunk.id] = chunk
        fused_scores[chunk.id] = fused_scores.get(chunk.id, 0.0) + 1.0 / (RRF_K + rank + 1)

    ranked_ids = sorted(fused_scores, key=lambda cid: fused_scores[cid], reverse=True)
    return [
        ChunkSearchResult(chunk=chunks_by_id[cid], fused_score=fused_scores[cid])
        for cid in ranked_ids[:limit]
    ]


async def semantic_fallback_search_chunks(
    chunk_repo: ChunkRepository,
    eval_ref_repo: EvalCriteriaReferenceRepository,
    llm: LLMProvider,
    bid_notice_id: int,
    limit: int = 5,
) -> list[ChunkSearchResult]:
    """하드 필터(app/rag/chunking/table_filter.py)가 평가기준표 청크를 하나도 못 찾았을 때 쓰는
    세컨드 티어 검색. '평가기준표가 어떤 모습인지' 보여주는 참조 코퍼스(EvalCriteriaReference)
    각각을 쿼리 삼아 해당 bid_notice의 청크를 dense 검색하고, 참조별 순위를 RRF로 합산한다.
    참조 코퍼스가 비어있으면(최초 호출 등) md 템플릿을 스캔해 즉시 임베딩·적재한다.
    """
    references = await ensure_seeded(eval_ref_repo.session, llm)
    if not references:
        return []

    fused_scores: dict[int, float] = {}
    chunks_by_id: dict[int, Chunk] = {}

    for reference in references:
        dense_results = await chunk_repo.dense_search(
            bid_notice_id, reference.embedding, limit=limit * 2
        )
        for rank, (chunk, _distance) in enumerate(dense_results):
            chunks_by_id[chunk.id] = chunk
            fused_scores[chunk.id] = fused_scores.get(chunk.id, 0.0) + 1.0 / (RRF_K + rank + 1)

    ranked_ids = sorted(fused_scores, key=lambda cid: fused_scores[cid], reverse=True)
    return [
        ChunkSearchResult(chunk=chunks_by_id[cid], fused_score=fused_scores[cid])
        for cid in ranked_ids[:limit]
    ]
