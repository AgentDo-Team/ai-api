from __future__ import annotations

import math
from dataclasses import dataclass
from collections.abc import Sequence

import numpy as np
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.db.models.company import CompanyProfile, CompanyProject
from app.db.repositories.chunk_repository import ChunkRepository
from app.schemas.second_filter import NoticeSoftResult, RankedChunk, SecondFilterResult
from app.services import embedding_service

RRF_K = 60
DOMAIN_TOPICS = ["개요", "요구사항"]
PREVIEW_LEN = 120
DEFAULT_CANDIDATE_K = 50
DEFAULT_FINAL_K = 10


@dataclass
class _Target:
    """유사도 비교 기준이 되는 자사 항목(프로필 또는 프로젝트 1건).

    embedding 은 dense(코사인) 쿼리에, text 는 BM25(렉시컬) 쿼리에 쓴다.
    text 는 임베딩을 만들 때 쓴 문장과 같아 dense/BM25 가 같은 대상을 가리킨다.
    """

    source: str  
    id: int
    embedding: list[float]
    text: str


def _cosine_distance(a: Sequence[float], b: Sequence[float]) -> float:
    va = np.asarray(a, dtype=np.float32)
    vb = np.asarray(b, dtype=np.float32)
    norm_a = float(np.linalg.norm(va))
    norm_b = float(np.linalg.norm(vb))
    if norm_a == 0.0 or norm_b == 0.0:
        return 1.0
    return 1.0 - float(np.dot(va, vb)) / (norm_a * norm_b)


def _nearest_target(
    embedding: Sequence[float] | None, targets: list[_Target]
) -> tuple[str, int] | None:
    if embedding is None or len(embedding) == 0:
        return None
    best: tuple[str, int] | None = None
    best_distance = math.inf
    for target in targets:
        distance = _cosine_distance(embedding, target.embedding)
        if distance < best_distance:
            best_distance = distance
            best = (target.source, target.id)
    return best


def _dedupe_exact_project_targets(targets: list[_Target]) -> list[_Target]:
    seen_project_texts: set[str] = set()
    unique: list[_Target] = []
    for target in targets:
        if target.source != "project":
            unique.append(target)
            continue
        if target.text in seen_project_texts:
            continue
        seen_project_texts.add(target.text)
        unique.append(target)
    return unique


class SecondFilterService:
    def __init__(
        self,
        session: AsyncSession,
        chunk_repo: ChunkRepository | None = None,
        *,
        rrf_k: int = RRF_K,
    ) -> None:
        if rrf_k < 1:
            raise ValueError("rrf_k must be positive")
        self.session = session
        self.chunk_repo = chunk_repo or ChunkRepository(session)
        self.rrf_k = rrf_k

    async def run(
        self,
        search_set_id: int,
        company_id: int,
        bid_notice_ids: list[int],
        query_text: str | None = None,
        candidate_k: int = DEFAULT_CANDIDATE_K,
        final_k: int = DEFAULT_FINAL_K,
    ) -> SecondFilterResult:
        if candidate_k < 1 or final_k < 1:
            raise ValueError("candidate_k and final_k must be positive")
        if final_k > candidate_k:
            raise ValueError("final_k must not exceed candidate_k")

        targets = await self._load_targets(company_id)
        sparse_by_text = await self._batch_sparse(
            bid_notice_ids, targets, query_text, candidate_k
        )

        results: list[NoticeSoftResult] = []
        for notice_id in bid_notice_ids:
            candidates = (
                await self._rank_chunks(
                    notice_id, targets, query_text, candidate_k, sparse_by_text
                )
                if targets
                else []
            )
            ranked = candidates[:final_k]
            aggregate = sum(rc.score for rc in ranked)
            results.append(
                NoticeSoftResult(
                    bid_notice_id=notice_id,
                    aggregate_score=round(aggregate, 6),
                    ranked_chunks=ranked,
                )
            )

        results.sort(key=lambda r: r.aggregate_score, reverse=True)
        return SecondFilterResult(
            search_set_id=search_set_id, company_id=company_id, results=results
        )

    async def _load_targets(self, company_id: int) -> list[_Target]:
        profile = (
            await self.session.exec(
                select(CompanyProfile).where(
                    CompanyProfile.company_id == company_id,
                    CompanyProfile.embedding.is_not(None),
                )
            )
        ).first()
        projects = (
            await self.session.exec(
                select(CompanyProject).where(
                    CompanyProject.company_id == company_id,
                    CompanyProject.embedding.is_not(None),
                ).order_by(CompanyProject.id)
            )
        ).all()

        targets: list[_Target] = []
        if profile:
            targets.append(
                _Target(
                    "profile",
                    profile.id,
                    profile.embedding,
                    embedding_service.profile_text(profile),
                )
            )
        for project in projects:
            targets.append(
                _Target(
                    "project",
                    project.id,
                    project.embedding,
                    embedding_service.project_text(project),
                )
            )
        return _dedupe_exact_project_targets(targets)

    async def _batch_sparse(
        self,
        bid_notice_ids: list[int],
        targets: list[_Target],
        query_text: str | None,
        candidate_k: int,
    ) -> dict[str, dict[int, list[tuple[object, float]]]]:
        fetch = candidate_k * 2
        texts = {target.text for target in targets if target.text.strip()}
        if query_text and query_text.strip():
            texts.add(query_text)

        sparse_by_text: dict[str, dict[int, list[tuple[object, float]]]] = {}
        for txt in sorted(texts):
            sparse_by_text[txt] = await self.chunk_repo.sparse_search_multi(
                bid_notice_ids, txt, per_notice_limit=fetch, l_topics=DOMAIN_TOPICS
            )
        return sparse_by_text

    async def _rank_chunks(
        self,
        bid_notice_id: int,
        targets: list[_Target],
        query_text: str | None,
        candidate_k: int,
        sparse_by_text: dict[str, dict[int, list[tuple[object, float]]]],
    ) -> list[RankedChunk]:
        fetch = candidate_k * 2  

        fused: dict[int, float] = {}
        chunk_by_id: dict[int, object] = {}

        def fuse(chunk, rank: int) -> None:
            chunk_by_id[chunk.id] = chunk
            fused[chunk.id] = fused.get(chunk.id, 0.0) + 1.0 / (
                self.rrf_k + rank + 1
            )

        for target in targets:
            dense = await self.chunk_repo.dense_search(
                bid_notice_id, target.embedding, limit=fetch, l_topics=DOMAIN_TOPICS
            )
            for rank, (chunk, _distance) in enumerate(dense):
                fuse(chunk, rank)

            if target.text.strip():
                lexical = sparse_by_text.get(target.text, {}).get(bid_notice_id, [])
                for rank, (chunk, _score) in enumerate(lexical):
                    fuse(chunk, rank)
        if query_text and query_text.strip():
            steer = sparse_by_text.get(query_text, {}).get(bid_notice_id, [])
            for rank, (chunk, _score) in enumerate(steer):
                fuse(chunk, rank)

        ranked: list[RankedChunk] = []
        for chunk_id in sorted(fused, key=lambda cid: (-fused[cid], cid)):
            if len(ranked) >= candidate_k:
                break
            chunk = chunk_by_id[chunk_id]
            matched = _nearest_target(getattr(chunk, "embedding", None), targets)
            if matched is None:
                continue
            source, matched_id = matched
            metadata = getattr(chunk, "chunk_metadata", None) or {}
            content = getattr(chunk, "content", None) or ""
            ranked.append(
                RankedChunk(
                    chunk_id=chunk_id,
                    rank=len(ranked) + 1,
                    score=round(fused[chunk_id], 6),
                    matched_source=source,
                    matched_id=matched_id,
                    l_topic=metadata.get("l_topic"),
                    preview=content[:PREVIEW_LEN] or None,
                )
            )
        return ranked
