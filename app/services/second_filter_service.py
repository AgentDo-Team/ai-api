"""2차 소프트필터(하이브리드 검색) 서비스.

하드필터(1차)를 통과한 공고들의 **개요·요구사항** 청크를 자사 프로필/프로젝트와
유사도 비교해 공고별 상위 매칭 청크(ranked_chunks)와 매칭도(aggregate_score)를 낸다.

랭킹(2층 구조):
  - 1층 기본(대칭 하이브리드): 타깃(프로필 1건 + 프로젝트 N건)마다 같은 대상을
    dense(임베딩 코사인) + BM25(텍스트 렉시컬) 두 방식으로 검색 → "우리 역량과 얼마나 맞나".
  - 2층 스티어링: 자유형식 메시지(있으면)를 BM25 로 한 번 더 검색해 매칭 청크를
    soft 가점한다(공고 제외 없이 순위만 끌어올림). 회사 정체성과 검색 의도를 분리.
  - 모든 순위 리스트를 RRF(Reciprocal Rank Fusion)로 합산.
  - 매칭 타깃(matched_source/matched_id)은 순위가 아니라 청크 임베딩과 각 타깃의
    실제 코사인 거리로 귀속한다(가장 가까운 프로필/프로젝트. 임베딩 없는 청크는 제외).

출력은 3차 필터 입력 shape(app/schemas/third_filter.py)과 정렬돼 있다.
청크 임베딩이 아직 없으면(팀원1 적재 전) dense/sparse 가 빈 결과라 ranked_chunks 도
비어서 나온다 — 파이프라인은 그대로 도는 상태.
"""

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

# RRF 상수 (hybrid_search.py 와 동일). 순위 기반이라 dense/BM25 점수 스케일 차이를 흡수한다.
RRF_K = 60
# 소프트필터 도메인 스코프: 사업개요·요구사항 청크만 비교 대상으로 삼는다.
DOMAIN_TOPICS = ["개요", "요구사항"]
PREVIEW_LEN = 120


@dataclass
class _Target:
    """유사도 비교 기준이 되는 자사 항목(프로필 또는 프로젝트 1건).

    embedding 은 dense(코사인) 쿼리에, text 는 BM25(렉시컬) 쿼리에 쓴다.
    text 는 임베딩을 만들 때 쓴 문장과 같아 dense/BM25 가 같은 대상을 가리킨다.
    """

    source: str  # "profile" | "project"
    id: int
    embedding: list[float]
    text: str


def _cosine_distance(a: Sequence[float], b: Sequence[float]) -> float:
    """pgvector 와 동일한 코사인 거리(1 - 코사인 유사도). 크기가 0이면 최대 거리(1.0).

    numpy 로 계산한다(1024차원을 파이썬 루프로 돌면 느려 병목이 된다).
    """
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
    """청크 임베딩과 코사인 거리가 가장 가까운 타깃의 (source, id). 임베딩 없으면 None."""
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


class SecondFilterService:
    def __init__(
        self,
        session: AsyncSession,
        chunk_repo: ChunkRepository | None = None,
    ) -> None:
        self.session = session
        self.chunk_repo = chunk_repo or ChunkRepository(session)

    async def run(
        self,
        search_set_id: int,
        company_id: int,
        bid_notice_ids: list[int],
        query_text: str | None = None,
        top_k: int = 5,
    ) -> SecondFilterResult:
        """하드필터 통과 공고들에 대해 2차 소프트필터를 수행한다.

        매칭도(aggregate_score) 내림차순으로 정렬해 돌려준다.
        """
        # 회사 입력폼의 지연 임베딩은 상위 검색 오케스트레이션이 한 번만 수행한다.
        targets = await self._load_targets(company_id)

        # BM25 는 쿼리당 고정 오버헤드(~150ms)가 커서 공고마다 반복하면 느리다.
        # 쿼리 텍스트별로 전 공고를 한 번에 배치 검색해 그 비용을 최소화한다.
        sparse_by_text = await self._batch_sparse(
            bid_notice_ids, targets, query_text, top_k
        )

        results: list[NoticeSoftResult] = []
        for notice_id in bid_notice_ids:
            ranked = (
                await self._rank_chunks(
                    notice_id, targets, query_text, top_k, sparse_by_text
                )
                if targets
                else []
            )
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
        """임베딩된 자사 프로필(1) + 프로젝트(N)를 비교 타깃으로 로드한다."""
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
                )
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
        return targets

    async def _batch_sparse(
        self,
        bid_notice_ids: list[int],
        targets: list[_Target],
        query_text: str | None,
        top_k: int,
    ) -> dict[str, dict[int, list[tuple[object, float]]]]:
        """쿼리 텍스트별(타깃 텍스트들 + 자유형식 메시지)로 전 공고 BM25 를 배치 검색한다.

        반환: {query_text: {bid_notice_id: [(Chunk, score)]}}. 같은 텍스트는 1회만 검색.
        """
        fetch = top_k * 2
        texts = {target.text for target in targets if target.text.strip()}
        if query_text and query_text.strip():
            texts.add(query_text)

        sparse_by_text: dict[str, dict[int, list[tuple[object, float]]]] = {}
        for txt in texts:
            sparse_by_text[txt] = await self.chunk_repo.sparse_search_multi(
                bid_notice_ids, txt, per_notice_limit=fetch, l_topics=DOMAIN_TOPICS
            )
        return sparse_by_text

    async def _rank_chunks(
        self,
        bid_notice_id: int,
        targets: list[_Target],
        query_text: str | None,
        top_k: int,
        sparse_by_text: dict[str, dict[int, list[tuple[object, float]]]],
    ) -> list[RankedChunk]:
        """한 공고의 개요·요구사항 청크를 두 층으로 랭킹한다.

        1층(기본, 대칭 하이브리드): 타깃(프로필/프로젝트)마다 같은 대상을 dense(임베딩)와
          BM25(텍스트) 두 방식으로 검색 → "이 공고가 우리 역량과 얼마나 맞나".
        2층(스티어링): 자유형식 메시지를 BM25 로 한 번 더 검색해 매칭 청크를 가점(soft).
          공고를 제외하지 않고 순위만 끌어올린다.

        BM25 결과는 sparse_by_text 로 미리 배치 계산된 것을 공고별로 꺼내 쓴다.
        모든 순위 리스트를 RRF 로 합산한다. 매칭 타깃(profile/project)은 순위가 아니라
        청크 임베딩과의 실제 코사인 거리로 귀속한다(임베딩 없는 청크는 제외).
        """
        fetch = top_k * 2  # 융합 여유분

        fused: dict[int, float] = {}
        chunk_by_id: dict[int, object] = {}

        def fuse(chunk, rank: int) -> None:
            chunk_by_id[chunk.id] = chunk
            fused[chunk.id] = fused.get(chunk.id, 0.0) + 1.0 / (RRF_K + rank + 1)

        # 1층: 타깃마다 dense(임베딩, 공고 단위) + BM25(텍스트, 배치 결과 조회)
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

        # 2층: 자유형식 메시지 BM25 스티어링(soft 가점) — 매칭 청크 순위만 끌어올림
        if query_text and query_text.strip():
            steer = sparse_by_text.get(query_text, {}).get(bid_notice_id, [])
            for rank, (chunk, _score) in enumerate(steer):
                fuse(chunk, rank)

        # 융합 점수 내림차순으로, 매칭 타깃(코사인 최근접)을 붙여 top_k 조립.
        # 임베딩이 없는 청크(BM25-only 등)는 타깃 귀속이 불가하므로 건너뛴다.
        ranked: list[RankedChunk] = []
        for chunk_id in sorted(fused, key=lambda cid: fused[cid], reverse=True):
            if len(ranked) >= top_k:
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
