"""bge-m3 임베딩 모델 래퍼 (FlagEmbedding).

dense(1024차원 밀집 벡터)와 sparse(lexical_weights, 희소 벡터)를 함께 뽑는다.
모델은 무겁기 때문에 프로세스당 한 번만 로드해 재사용한다(get_model).
"""

from functools import lru_cache
from typing import TypedDict

from FlagEmbedding import BGEM3FlagModel

MODEL_NAME = "BAAI/bge-m3"
EMBED_DIM = 1024


class EmbedResult(TypedDict):
    dense: list[float]  # 밀집 벡터 (1024차원)
    sparse: dict[str, float]  # 희소 벡터 (토큰ID → 가중치)


@lru_cache(maxsize=1)
def get_model() -> BGEM3FlagModel:
    """bge-m3 모델을 로드한다. 최초 1회만 실제 로드되고 이후 캐시된 객체를 재사용."""
    # use_fp16: 반정밀도로 로드해 메모리·속도 이득 (정확도 손실은 미미)
    return BGEM3FlagModel(MODEL_NAME, use_fp16=True)


def embed_texts(texts: list[str]) -> list[EmbedResult]:
    """텍스트 목록을 dense/sparse 벡터로 임베딩한다.

    입력 순서와 출력 순서는 1:1로 대응한다.
    """
    model = get_model()
    output = model.encode(
        texts,
        return_dense=True,
        return_sparse=True,
        return_colbert_vecs=False,  # ColBERT(다중 벡터)는 사용하지 않음
    )

    dense_vecs = output["dense_vecs"]  # numpy 배열 (len(texts), 1024)
    lexical_weights = output["lexical_weights"]  # 각 텍스트별 {토큰ID: 가중치}

    results: list[EmbedResult] = []
    for index in range(len(texts)):
        results.append(
            {
                "dense": dense_vecs[index].tolist(),
                # JSONB 저장·직렬화를 위해 키는 str, 값은 float로 변환
                "sparse": {
                    str(token_id): float(weight)
                    for token_id, weight in lexical_weights[index].items()
                },
            }
        )
    return results
 