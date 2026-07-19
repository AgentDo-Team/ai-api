from types import SimpleNamespace

import pytest
from pydantic import ValidationError

from scripts.evaluation.second_filter_benchmark import (
    EvaluationCase,
    Ranking,
    calculate_metrics,
    embedding_sha256,
    rank_notices,
    retrieve_scenario,
    validate_target_snapshot,
)
from app.services.second_filter_service import _Target


def make_case() -> EvaluationCase:
    return EvaluationCase(
        case_id="case-001",
        company_id=2,
        bid_notice_ids=[10, 20],
        message="AI 플랫폼",
        notice_relevance={10: 3, 20: 1},
        chunk_relevance={10: {101: 3, 102: 1}, 20: {201: 2}},
    )


def test_case_requires_labels_for_every_notice():
    with pytest.raises(ValidationError, match="every bid_notice_id"):
        EvaluationCase(
            case_id="bad",
            company_id=1,
            bid_notice_ids=[10, 20],
            notice_relevance={10: 3},
            chunk_relevance={},
        )


def test_rank_notices_uses_sum_of_final_chunk_scores():
    ranked, scores = rank_notices(
        {10: Ranking([1, 2], [0.3, 0.2]), 20: Ranking([3], [0.4])}, final_k=10
    )
    assert ranked == [10, 20]
    assert scores == {10: pytest.approx(0.5), 20: pytest.approx(0.4)}


def test_rank_notices_supports_offline_aggregate_alternatives():
    rankings = {
        10: Ranking([1, 2, 3], [0.3, 0.2, 0.1]),
        20: Ranking([4, 5, 6], [0.4, 0.05, 0.01]),
    }

    ranked_max, _ = rank_notices(rankings, final_k=3, aggregate_method="max")
    ranked_top3, scores_top3 = rank_notices(
        rankings, final_k=3, aggregate_method="sum_top_3"
    )
    ranked_discounted, _ = rank_notices(
        rankings, final_k=3, aggregate_method="discounted_sum"
    )

    assert ranked_max == [20, 10]
    assert ranked_top3 == [10, 20]
    assert scores_top3[10] == pytest.approx(0.6)
    assert ranked_discounted == [10, 20]


def test_metrics_include_notice_and_macro_chunk_quality():
    case = make_case()
    rankings = {
        10: Ranking([101, 999, 102], [0.3, 0.2, 0.1]),
        20: Ranking([999, 201], [0.2, 0.1]),
    }
    metrics = calculate_metrics(case, rankings, [10, 20], candidate_k=20)
    assert metrics["chunk_recall_at_10"] == pytest.approx(1.0)
    assert metrics["chunk_mrr"] == pytest.approx(0.75)
    assert metrics["chunk_candidate_recall"] == pytest.approx(1.0)
    assert metrics["notice_mrr"] == pytest.approx(1.0)
    assert metrics["notice_ndcg_at_10"] == pytest.approx(1.0)
    assert metrics["chunk_recall_at_50"] is None
    assert metrics["chunk_recall_at_10_rel2"] == pytest.approx(1.0)
    assert metrics["chunk_recall_at_10_rel3"] == pytest.approx(1.0)
    assert metrics["chunk_hit_rate_at_10_rel3"] == pytest.approx(1.0)
    assert metrics["chunk_mrr_rel3"] == pytest.approx(1.0)


def test_snapshot_detects_changed_company_input():
    target = _Target("profile", 1, [1.0], "현재 프로필")
    data = make_case().model_dump()
    data["target_snapshot"] = [
        {
            "source": "profile",
            "id": 1,
            "text": "이전 프로필",
            "embedding_sha256": embedding_sha256([1.0]),
        }
    ]
    case = EvaluationCase.model_validate(data)
    with pytest.raises(ValueError, match="changed after labeling"):
        validate_target_snapshot(case, [target])


class FakeRepo:
    def __init__(self):
        self.calls = []

    async def sparse_search_multi(self, notice_ids, text, per_notice_limit, l_topics):
        self.calls.append((notice_ids, text, per_notice_limit))
        return {
            notice_id: [(SimpleNamespace(id=notice_id * 10 + 1), 1.0)]
            for notice_id in notice_ids
        }


async def test_bm25_batches_all_notices_per_query_text():
    repo = FakeRepo()
    service = SimpleNamespace(chunk_repo=repo)
    targets = [_Target("profile", 1, [1.0], "회사 역량")]
    result = await retrieve_scenario(
        service, [10, 20], "AI 우선", "bm25", targets, candidate_k=5
    )
    assert len(repo.calls) == 2
    assert all(call[0] == [10, 20] for call in repo.calls)
    assert set(result) == {10, 20}
