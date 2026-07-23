from __future__ import annotations

from typing import TypeVar

from langchain_openai import ChatOpenAI
from openai import AsyncOpenAI
from pydantic import BaseModel

from app.core.config import settings
from app.llm.base import LLMProvider

T = TypeVar("T", bound=BaseModel)


class OpenAIProvider(LLMProvider):
    def __init__(self, client: AsyncOpenAI | None = None, chat: ChatOpenAI | None = None) -> None:
        self.client = client or AsyncOpenAI(api_key=settings.openai_api_key)
        self._injected_chat = chat
        self._chats: dict[str, ChatOpenAI] = {}

    def _chat_for(self, model: str) -> ChatOpenAI:
        if self._injected_chat is not None:
            return self._injected_chat
        if model not in self._chats:
            self._chats[model] = ChatOpenAI(model=model, api_key=settings.openai_api_key)
        return self._chats[model]

    async def complete_structured(
        self, *, system: str, user: str, response_model: type[T], model: str | None = None
    ) -> T:
        completion = await self.client.chat.completions.parse(
            model=model or settings.llm_model,
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

    async def complete_structured_batch(
        self, *, requests: list[tuple[str, str]], response_model: type[T], model: str | None = None
    ) -> list[T]:
        if not requests:
            return []
        structured_llm = self._chat_for(model or settings.llm_model).with_structured_output(
            response_model
        )
        batch_inputs = [
            [("system", system), ("user", user)] for system, user in requests
        ]
        return await structured_llm.abatch(batch_inputs)

    async def embed(self, text: str) -> list[float]:
        response = await self.client.embeddings.create(
            model=settings.embedding_model,
            input=text,
            dimensions=settings.embedding_dim,
        )
        return response.data[0].embedding
