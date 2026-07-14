"""로컬 Ollama에 올라간 BGE-M3 임베딩 모델 클라이언트."""

import logging

import httpx

from app.core.config import settings

logger = logging.getLogger(__name__)


class OllamaEmbedder:
    """Ollama `/api/embed` 엔드포인트로 밀집 벡터를 얻는다."""

    def __init__(
        self,
        base_url: str | None = None,
        model: str | None = None,
        dim: int | None = None,
        timeout: float | None = None,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        self.base_url = (base_url or settings.ollama_base_url).rstrip("/")
        self.model = model or settings.embedding_model
        self.dim = dim or settings.embedding_dim
        self.timeout = timeout or settings.embedding_timeout
        self._client = client

    async def embed(self, text: str) -> list[float]:
        payload = {"model": self.model, "input": text}

        if self._client is not None:
            response = await self._client.post(
                f"{self.base_url}/api/embed", json=payload, timeout=self.timeout
            )
        else:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.post(f"{self.base_url}/api/embed", json=payload)

        response.raise_for_status()
        embeddings = response.json().get("embeddings") or []
        if not embeddings:
            raise ValueError(f"Ollama가 빈 임베딩을 반환했습니다. (model={self.model})")

        vector = embeddings[0]
        if len(vector) != self.dim:
            raise ValueError(
                f"임베딩 차원이 맞지 않습니다. expected={self.dim}, actual={len(vector)} "
                f"(model={self.model})"
            )
        return vector
