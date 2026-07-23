from typing import TypedDict

from openai import AsyncOpenAI, OpenAIError

from app.common.exceptions import AppException
from app.core.config import settings

_TIMEOUT_SECONDS = 60.0
_client = AsyncOpenAI(api_key=settings.openai_api_key, timeout=_TIMEOUT_SECONDS)


class EmbedVector(TypedDict):
    dense: list[float]  


async def embed_texts(texts: list[str]) -> list[EmbedVector]:
    if not texts:
        return []

    try:
        response = await _client.embeddings.create(
            model=settings.embedding_model,
            dimensions=settings.embedding_dim,
            input=texts,
        )
    except OpenAIError as exc:
        raise AppException(
            f"OpenAI 임베딩 호출에 실패했습니다: {exc}", status_code=502
        ) from exc
    ordered = sorted(response.data, key=lambda item: item.index)
    return [{"dense": item.embedding} for item in ordered]
