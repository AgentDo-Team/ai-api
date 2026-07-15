"""OpenAI 임베딩 호출 클라이언트.

dense 벡터는 OpenAI `text-embedding-3-small`(dimensions=1024)로 뽑는다.
렉시컬(정확 용어) 매칭은 chunks.content BM25(pg_search)가 담당하므로
희소벡터는 만들지 않고 dense만 반환한다.

주의: 텍스트가 OpenAI(외부 API)로 전송된다. 청크·자사 프로필/프로젝트가 반출되므로
데이터 정책이 허용되는 전제에서만 사용한다.
"""

from typing import TypedDict

from openai import AsyncOpenAI, OpenAIError

from app.common.exceptions import AppException
from app.core.config import settings

# 임베딩은 무거운 연산이라 타임아웃을 넉넉히 둔다.
_TIMEOUT_SECONDS = 60.0

# api_key=None이면 SDK가 OPENAI_API_KEY 환경변수를 자동으로 읽는다.
_client = AsyncOpenAI(api_key=settings.openai_api_key, timeout=_TIMEOUT_SECONDS)


class EmbedVector(TypedDict):
    dense: list[float]  # 밀집 벡터 (embedding_dim 차원)


async def embed_texts(texts: list[str]) -> list[EmbedVector]:
    """텍스트 목록을 OpenAI 임베딩으로 dense 벡터화한다.

    입력 순서와 출력 순서는 1:1로 대응한다. 빈 목록이면 API를 호출하지 않는다.
    팀원1의 문서 청크 임베딩도 벡터 공간을 맞추려면 이 함수를 그대로 재사용해야 한다.
    (같은 모델 `settings.embedding_model` + 같은 차원 `settings.embedding_dim`)
    """
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

    # response.data는 요청 순서를 보장하지 않으므로 index로 정렬한다.
    ordered = sorted(response.data, key=lambda item: item.index)
    return [{"dense": item.embedding} for item in ordered]
