"""CPU-only ONNX INT8 reranker used by the offline retrieval benchmark."""

from __future__ import annotations

from pathlib import Path

import numpy as np
from sentence_transformers import CrossEncoder


class BgeOnnxInt8Reranker:
    """Load a locally exported BGE CrossEncoder without network access."""

    def __init__(
        self,
        model_path: Path,
        *,
        batch_size: int = 8,
        max_length: int = 512,
    ) -> None:
        self.model_path = model_path
        self.batch_size = batch_size
        self.max_length = max_length
        self._model: CrossEncoder | None = None

    def load(self) -> None:
        if self._model is not None:
            return
        if not self.model_path.exists():
            raise FileNotFoundError(
                f"ONNX reranker not found: {self.model_path}. "
                "Run scripts.evaluation.export_bge_onnx_int8 first."
            )
        onnx_files = sorted(self.model_path.rglob("*qint8*.onnx"))
        if not onnx_files:
            raise FileNotFoundError(
                f"No qint8 ONNX file found below {self.model_path}"
            )
        relative_onnx = onnx_files[0].relative_to(self.model_path).as_posix()
        self._model = CrossEncoder(
            str(self.model_path),
            backend="onnx",
            device="cpu",
            local_files_only=True,
            max_length=self.max_length,
            model_kwargs={"file_name": relative_onnx},
        )

    def score_pairs(self, pairs: list[tuple[str, str]]) -> list[float]:
        self.load()
        if not pairs:
            return []
        assert self._model is not None
        raw = np.asarray(
            self._model.predict(
                pairs,
                batch_size=self.batch_size,
                show_progress_bar=False,
                convert_to_numpy=True,
            ),
            dtype=np.float64,
        ).reshape(-1)
        # CrossEncoder applies the model's default sigmoid activation already.
        # Applying sigmoid again would collapse unrelated scores toward 0.5.
        return [float(value) for value in raw]
