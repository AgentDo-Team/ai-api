from pathlib import Path

import numpy as np

from scripts.evaluation.bge_onnx_reranker import BgeOnnxInt8Reranker


class FakeCrossEncoder:
    def predict(self, pairs, **kwargs):
        assert len(pairs) == 2
        return np.asarray([0.2, 0.8])


def test_score_pairs_preserves_cross_encoder_normalized_scores():
    reranker = BgeOnnxInt8Reranker(Path("unused"))
    reranker._model = FakeCrossEncoder()  # type: ignore[assignment]

    scores = reranker.score_pairs([("q1", "d1"), ("q2", "d2")])

    assert scores == [0.2, 0.8]
