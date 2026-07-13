"""bge-m3 임베딩 서빙 (FastAPI).

메인 API와 분리된 별도 서비스. torch·모델이 무거워 독립 프로세스로 띄운다.
실행: uv run --extra embedding uvicorn embedding_server.main:app --port 8001
"""

from contextlib import asynccontextmanager

from fastapi import FastAPI
from pydantic import BaseModel, Field

from embedding_server.embedder import EMBED_DIM, MODEL_NAME, embed_texts, get_model


class EmbedRequest(BaseModel):
    texts: list[str] = Field(min_length=1, description="임베딩할 텍스트 목록")


class EmbedItem(BaseModel):
    dense: list[float]  # 밀집 벡터 (1024차원)
    sparse: dict[str, float]  # 희소 벡터 (토큰ID → 가중치)


class EmbedResponse(BaseModel):
    model: str
    dim: int
    results: list[EmbedItem]


@asynccontextmanager
async def lifespan(app: FastAPI):
    # 서버 기동 시 모델을 미리 로드해, 첫 요청이 느려지지 않게 한다(warm-up)
    get_model()
    yield


app = FastAPI(title="bge-m3-embedding-server", lifespan=lifespan)


@app.get("/health")
def health_check() -> dict:
    return {"status": "ok", "model": MODEL_NAME}


@app.post("/embed", response_model=EmbedResponse)
def embed(request: EmbedRequest) -> EmbedResponse:
    """텍스트를 dense/sparse 벡터로 임베딩해 반환한다.

    동기 함수라 FastAPI가 스레드풀에서 실행 → 이벤트 루프를 막지 않는다.
    """
    results = embed_texts(request.texts)
    return EmbedResponse(model=MODEL_NAME, dim=EMBED_DIM, results=results)
