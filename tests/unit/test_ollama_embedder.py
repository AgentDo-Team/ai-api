"""OllamaEmbedder 테스트. httpx.MockTransport 로 응답을 대신하므로 실제 Ollama가 필요 없다."""

import json

import httpx
import pytest

from app.rag.embeddings.ollama import OllamaEmbedder


def make_embedder(handler, **kwargs) -> OllamaEmbedder:
    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    return OllamaEmbedder(
        base_url="http://localhost:11434",
        model="bge-m3",
        dim=1024,
        client=client,
        **kwargs,
    )


async def test_embed_posts_bge_m3_payload_and_returns_vector():
    seen: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["url"] = str(request.url)
        seen["body"] = json.loads(request.content)
        return httpx.Response(200, json={"embeddings": [[0.5] * 1024]})

    vector = await make_embedder(handler).embed("주력기술: AI")

    assert seen["url"] == "http://localhost:11434/api/embed"
    assert seen["body"] == {"model": "bge-m3", "input": "주력기술: AI"}
    assert len(vector) == 1024
    assert vector[0] == 0.5


async def test_embed_raises_on_dimension_mismatch():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"embeddings": [[0.5] * 768]})

    with pytest.raises(ValueError, match="임베딩 차원이 맞지 않습니다"):
        await make_embedder(handler).embed("텍스트")


async def test_embed_raises_on_empty_embeddings():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"embeddings": []})

    with pytest.raises(ValueError, match="빈 임베딩"):
        await make_embedder(handler).embed("텍스트")


async def test_embed_raises_on_http_error():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(404, json={"error": "model not found"})

    with pytest.raises(httpx.HTTPStatusError):
        await make_embedder(handler).embed("텍스트")
