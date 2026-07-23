from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TypeVar

from pydantic import BaseModel

T = TypeVar("T", bound=BaseModel)


class LLMProvider(ABC):
    @abstractmethod
    async def complete_structured(
        self, *, system: str, user: str, response_model: type[T], model: str | None = None
    ) -> T:
        """system/user 프롬프트로 LLM 을 호출하고, response_model 스키마에 맞는 구조화 출력을 반환한다.

        model 을 주면 그 모델로, 없으면 settings.llm_model 로 호출한다.
        """

    @abstractmethod
    async def complete_structured_batch(
        self, *, requests: list[tuple[str, str]], response_model: type[T], model: str | None = None
    ) -> list[T]:
        """(system, user) 프롬프트 쌍 여러 건을 한 번의 배치 호출로 묶어 LLM 에 전송한다.

        반환 리스트의 순서는 requests 순서와 동일하다.
        model 을 주면 그 모델로, 없으면 settings.llm_model 로 호출한다.
        """

    @abstractmethod
    async def embed(self, text: str) -> list[float]:
        """텍스트를 임베딩한다. 반환 차원은 settings.embedding_dim 과 일치해야 한다."""
