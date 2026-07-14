"""임베딩 provider 공통 인터페이스."""

from typing import Protocol


class Embedder(Protocol):
    """텍스트 하나를 밀집 벡터로 변환한다.

    구현체는 실패 시 예외를 던진다. 예외를 삼킬지 말지는 호출자(서비스)가 정한다.
    """

    async def embed(self, text: str) -> list[float]: ...
