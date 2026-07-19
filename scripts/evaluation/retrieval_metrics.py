"""Pure metrics used by offline retrieval evaluation."""

from __future__ import annotations

import math
from collections.abc import Sequence


def recall_at_k(
    ranked_ids: Sequence[int],
    relevance: dict[int, int],
    k: int,
    min_relevance: int = 1,
) -> float:
    """min_relevance 이상인 정답 중 top-k에 포함된 비율."""
    relevant = {
        chunk_id for chunk_id, grade in relevance.items() if grade >= min_relevance
    }
    if not relevant:
        raise ValueError(f"관련도 {min_relevance} 이상인 정답 청크가 필요합니다.")
    retrieved = set(ranked_ids[:k])
    return len(relevant & retrieved) / len(relevant)


def hit_rate_at_k(
    ranked_ids: Sequence[int],
    relevance: dict[int, int],
    k: int,
    min_relevance: int = 1,
) -> float:
    """top-k에 기준 이상의 정답이 하나라도 있으면 1, 없으면 0."""
    relevant = {
        chunk_id for chunk_id, grade in relevance.items() if grade >= min_relevance
    }
    if not relevant:
        raise ValueError(f"관련도 {min_relevance} 이상인 정답 청크가 필요합니다.")
    return float(bool(relevant & set(ranked_ids[:k])))


def reciprocal_rank(
    ranked_ids: Sequence[int], relevance: dict[int, int], min_relevance: int = 1
) -> float:
    """첫 관련 청크 순위의 역수. 검색하지 못하면 0."""
    relevant = {
        chunk_id for chunk_id, grade in relevance.items() if grade >= min_relevance
    }
    if not relevant:
        raise ValueError(f"관련도 {min_relevance} 이상인 정답 청크가 필요합니다.")
    for rank, chunk_id in enumerate(ranked_ids, start=1):
        if chunk_id in relevant:
            return 1.0 / rank
    return 0.0


def ndcg_at_k(
    ranked_ids: Sequence[int], relevance: dict[int, int], k: int
) -> float:
    """등급형 관련도를 반영한 normalized DCG@K."""

    def dcg(grades: Sequence[int]) -> float:
        return sum(
            (2**grade - 1) / math.log2(rank + 1)
            for rank, grade in enumerate(grades, start=1)
        )

    actual = [relevance.get(chunk_id, 0) for chunk_id in ranked_ids[:k]]
    ideal = sorted((grade for grade in relevance.values() if grade > 0), reverse=True)[:k]
    ideal_score = dcg(ideal)
    return dcg(actual) / ideal_score if ideal_score else 0.0


def percentile(values: Sequence[float], percent: float) -> float:
    """외부 통계 의존성 없이 선형 보간 percentile을 계산한다."""
    if not values:
        raise ValueError("percentile을 계산할 값이 필요합니다.")
    if not 0 <= percent <= 100:
        raise ValueError("percent는 0 이상 100 이하여야 합니다.")
    ordered = sorted(values)
    position = (len(ordered) - 1) * percent / 100
    lower = math.floor(position)
    upper = math.ceil(position)
    if lower == upper:
        return float(ordered[lower])
    weight = position - lower
    return float(ordered[lower] * (1 - weight) + ordered[upper] * weight)
