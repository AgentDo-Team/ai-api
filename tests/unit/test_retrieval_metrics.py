import pytest

from scripts.evaluation.retrieval_metrics import (
    hit_rate_at_k,
    ndcg_at_k,
    percentile,
    recall_at_k,
    reciprocal_rank,
)


def test_recall_at_k():
    relevance = {10: 3, 20: 2, 30: 1}
    assert recall_at_k([10, 99, 20], relevance, 2) == pytest.approx(1 / 3)
    assert recall_at_k([10, 99, 20], relevance, 3) == pytest.approx(2 / 3)
    assert recall_at_k([10, 99, 20], relevance, 3, min_relevance=3) == 1.0


def test_hit_rate_at_k_with_relevance_threshold():
    relevance = {10: 3, 20: 2, 30: 1}
    assert hit_rate_at_k([99, 10], relevance, 2, min_relevance=3) == 1.0
    assert hit_rate_at_k([99, 20], relevance, 2, min_relevance=3) == 0.0


def test_reciprocal_rank():
    assert reciprocal_rank([99, 20, 10], {10: 3, 20: 1}) == pytest.approx(0.5)
    assert reciprocal_rank([99], {10: 3}) == 0.0


def test_ndcg_is_one_for_ideal_ranking():
    relevance = {10: 3, 20: 2, 30: 1}
    assert ndcg_at_k([10, 20, 30], relevance, 3) == pytest.approx(1.0)
    assert ndcg_at_k([30, 20, 10], relevance, 3) < 1.0


def test_percentile_uses_linear_interpolation():
    assert percentile([10, 20, 30, 40], 50) == pytest.approx(25)
    assert percentile([10, 20, 30, 40], 95) == pytest.approx(38.5)
