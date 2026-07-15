"""OpenAI 기반 LLMProvider 구현체."""

from __future__ import annotations

from typing import TypeVar

from openai import AsyncOpenAI
from pydantic import BaseModel

from app.core.config import settings
from app.llm.base import LLMProvider

T = TypeVar("T", bound=BaseModel)


class OpenAIProvider(LLMProvider):
    def __init__(self, client: AsyncOpenAI | None = None) -> None:
        self.client = client or AsyncOpenAI(api_key=settings.openai_api_key)

    async def complete_structured(self, *, system: str, user: str, response_model: type[T]) -> T:
        completion = await self.client.chat.completions.parse(
            model=settings.llm_model,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            response_format=response_model,
        )
        parsed = completion.choices[0].message.parsed
        if parsed is None:
            raise ValueError("LLM 구조화 출력 파싱 실패: parsed 결과가 없습니다.")
        return parsed

    async def embed(self, text: str) -> list[float]:
        response = await self.client.embeddings.create(
            model=settings.embedding_model,
            input=text,
            dimensions=settings.embedding_dim,
        )
        return response.data[0].embedding
