"""bge-m3 임베딩 서버(embedding_server) 호출 클라이언트.

메인 앱은 무거운 모델을 직접 들고 있지 않고, 별도 프로세스로 뜬 임베딩 서버에
HTTP로 텍스트를 보내 dense/sparse 벡터를 받아온다.
"""

from typing import TypedDict

import httpx

from app.common.exceptions import AppException
from app.core.config import settings

# 임베딩은 무거운 연산이라 타임아웃을 넉넉히 둔다.
_TIMEOUT_SECONDS = 60.0


class EmbedVector(TypedDict):
    dense: list[float]  # 밀집 벡터 (1024차원)
    sparse: dict[str, float]  # 희소 벡터 (토큰ID → 가중치)


async def embed_texts(texts: list[str]) -> list[EmbedVector]:
    """텍스트 목록을 임베딩 서버에 보내 dense/sparse 벡터를 받는다.

    입력 순서와 출력 순서는 1:1로 대응한다. 빈 목록이면 서버를 호출하지 않는다.
    """
    if not texts:
        return []

    url = settings.embedding_service_url.rstrip("/") + "/embed"
    try:
        async with httpx.AsyncClient(timeout=_TIMEOUT_SECONDS) as client:
            response = await client.post(url, json={"texts": texts})
            response.raise_for_status()
    except httpx.HTTPError as exc:
        raise AppException(
            f"임베딩 서버 호출에 실패했습니다: {exc}", status_code=502
        ) from exc

    return response.json()["results"]
