"""챗봇 채팅 세션 CRUD + 대화 엔드포인트 테스트.

get_chat_service / verify_company_access 를 갈아끼워 DB·LLM 없이
라우터·서비스 로직(세션 CRUD, 소유권 검증, 메시지 누적)만 검증한다.
"""

from typing import Any

import pytest
from httpx import ASGITransport, AsyncClient

from app.api.deps import get_chat_service, verify_company_access
from app.db.models.analysis import ChatMessage
from app.db.models.search import SearchSet
from app.services import chat_service as chat_service_module
from app.services.chat_service import ChatService
from main import app

COMPANY_ID = 1
OTHER_COMPANY_ID = 2


class FakeSession:
    def __init__(self) -> None:
        self.commits = 0

    async def commit(self) -> None:
        self.commits += 1

    async def refresh(self, entity: Any) -> None:
        pass


class FakeSearchSetRepository:
    def __init__(self) -> None:
        self.rows: dict[int, SearchSet] = {}
        self._next_id = 1

    async def add(self, search_set: SearchSet) -> SearchSet:
        if search_set.id is None:
            search_set.id = self._next_id
            self._next_id += 1
        self.rows[search_set.id] = search_set
        return search_set

    async def get(self, search_set_id: int) -> SearchSet | None:
        return self.rows.get(search_set_id)

    async def list_by_company(
        self, company_id: int, limit: int = 50, offset: int = 0
    ) -> list[SearchSet]:
        ordered = sorted(
            (s for s in self.rows.values() if s.company_id == company_id),
            key=lambda s: s.id,
            reverse=True,
        )
        return ordered[offset : offset + limit]

    async def delete(self, search_set: SearchSet) -> None:
        self.rows.pop(search_set.id, None)


class FakeChatMessageRepository:
    def __init__(self) -> None:
        self.rows: dict[int, ChatMessage] = {}
        self._next_id = 1

    async def add(self, message: ChatMessage) -> ChatMessage:
        if message.id is None:
            message.id = self._next_id
            self._next_id += 1
        self.rows[message.id] = message
        return message

    async def list_by_search_set(self, search_set_id: int) -> list[ChatMessage]:
        return sorted(
            (m for m in self.rows.values() if m.search_set_id == search_set_id),
            key=lambda m: m.id,
        )


@pytest.fixture
def search_set_repo() -> FakeSearchSetRepository:
    return FakeSearchSetRepository()


@pytest.fixture
def chat_message_repo() -> FakeChatMessageRepository:
    return FakeChatMessageRepository()


@pytest.fixture
async def client(search_set_repo, chat_message_repo):
    service = ChatService(
        session=FakeSession(),
        search_set_repo=search_set_repo,
        chat_message_repo=chat_message_repo,
    )
    app.dependency_overrides[get_chat_service] = lambda: service
    # CRUD/서비스 로직 검증에 집중하기 위해 JWT 인증(본인 회사 확인)은 우회한다.
    app.dependency_overrides[verify_company_access] = lambda: None
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as c:
        yield c
    app.dependency_overrides.clear()


@pytest.fixture
def session_of_company(search_set_repo) -> SearchSet:
    """COMPANY_ID 소유의 세션 1건을 저장소에 심는다."""
    s = SearchSet(id=1, company_id=COMPANY_ID, title="테스트 세션")
    search_set_repo.rows[1] = s
    search_set_repo._next_id = 2
    return s


@pytest.fixture
def other_session(search_set_repo) -> SearchSet:
    """다른 회사(OTHER_COMPANY_ID) 소유의 세션."""
    s = SearchSet(id=99, company_id=OTHER_COMPANY_ID, title="남의 세션")
    search_set_repo.rows[99] = s
    return s


# --------------------------------------------------------------------------- #
# 세션 CRUD
# --------------------------------------------------------------------------- #


async def test_list_sessions_newest_first(client, search_set_repo):
    # 세션은 검색 전송(create_search_session) 경로로만 생성되므로, 여기서는 저장소에 직접 심는다.
    for idx, title in enumerate(("첫 세션", "둘째 세션", "셋째 세션"), start=1):
        search_set_repo.rows[idx] = SearchSet(
            id=idx, company_id=COMPANY_ID, title=title
        )
    res = await client.get(f"/api/companies/{COMPANY_ID}/chat-sessions")
    assert res.status_code == 200
    titles = [s["title"] for s in res.json()["data"]]
    assert titles == ["셋째 세션", "둘째 세션", "첫 세션"]


async def test_list_sessions_scoped_to_company(client, other_session):
    res = await client.get(f"/api/companies/{COMPANY_ID}/chat-sessions")
    assert res.status_code == 200
    # 다른 회사 세션은 목록에 안 나온다.
    assert res.json()["data"] == []


async def test_rename_session(client, session_of_company):
    res = await client.patch(
        f"/api/companies/{COMPANY_ID}/chat-sessions/1", json={"title": "이름 변경됨"}
    )
    assert res.status_code == 200
    assert res.json()["data"]["title"] == "이름 변경됨"


async def test_rename_other_company_session_404(client, other_session):
    res = await client.patch(
        f"/api/companies/{COMPANY_ID}/chat-sessions/99", json={"title": "침범"}
    )
    assert res.status_code == 404


async def test_delete_session(client, session_of_company, search_set_repo):
    res = await client.delete(f"/api/companies/{COMPANY_ID}/chat-sessions/1")
    assert res.status_code == 200
    assert 1 not in search_set_repo.rows


async def test_delete_missing_session_404(client):
    res = await client.delete(f"/api/companies/{COMPANY_ID}/chat-sessions/12345")
    assert res.status_code == 404


# --------------------------------------------------------------------------- #
# 메시지 / 챗봇 대화
# --------------------------------------------------------------------------- #


async def test_list_messages_empty(client, session_of_company):
    res = await client.get(f"/api/companies/{COMPANY_ID}/chat-sessions/1/messages")
    assert res.status_code == 200
    assert res.json()["data"] == []


async def test_list_messages_other_company_404(client, other_session):
    res = await client.get(f"/api/companies/{COMPANY_ID}/chat-sessions/99/messages")
    assert res.status_code == 404


async def test_send_message_persists_and_replies(
    client, session_of_company, chat_message_repo, monkeypatch
):
    # LLM/RAG 호출은 네트워크·DB 를 타므로 가짜로 대체한다.
    async def fake_embedding(text: str):
        return [0.0]

    async def fake_build_company_context(session, company_id):
        return "회사 컨텍스트"

    class FakeChain:
        async def ainvoke(self, payload):
            return f"[답변] {payload['question']}"

    monkeypatch.setattr(chat_service_module, "embedding", fake_embedding)
    monkeypatch.setattr(
        chat_service_module, "build_company_context", fake_build_company_context
    )
    monkeypatch.setattr(chat_service_module, "my_gpt_chain", FakeChain())

    res = await client.post(
        f"/api/companies/{COMPANY_ID}/chat-sessions/1/messages",
        json={"question": "이 공고의 과업은?"},
    )
    assert res.status_code == 200
    data = res.json()["data"]
    assert data["role"] == "assistant"
    assert data["content"] == "[답변] 이 공고의 과업은?"

    # user + assistant 두 건이 세션에 쌓였는지 확인 (이전 세션 연결 기반).
    stored = await chat_message_repo.list_by_search_set(1)
    assert [m.role for m in stored] == ["user", "assistant"]
    assert stored[0].content == "이 공고의 과업은?"


async def test_send_message_other_company_404(client, other_session):
    res = await client.post(
        f"/api/companies/{COMPANY_ID}/chat-sessions/99/messages",
        json={"question": "침범"},
    )
    assert res.status_code == 404
