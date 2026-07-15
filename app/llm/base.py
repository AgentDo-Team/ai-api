"""LLM provider 공통 인터페이스.

구조화 출력(response_model)과 임베딩만 제공한다. 프리텍스트 completion 은
현재 파이프라인(평가기준 추출/채점)에서 쓰지 않아 인터페이스에 넣지 않았다.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TypeVar

from pydantic import BaseModel

T = TypeVar("T", bound=BaseModel)


class LLMProvider(ABC):
    @abstractmethod
    async def complete_structured(self, *, system: str, user: str, response_model: type[T]) -> T:
        """system/user 프롬프트로 LLM 을 호출하고, response_model 스키마에 맞는 구조화 출력을 반환한다."""

    @abstractmethod
    async def embed(self, text: str) -> list[float]:
        """텍스트를 임베딩한다. 반환 차원은 settings.embedding_dim 과 일치해야 한다."""
