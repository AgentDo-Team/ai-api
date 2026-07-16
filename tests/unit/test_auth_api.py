"""/auth/signup 단위 테스트.

DB 없이 get_session 을 fake 세션으로 갈아끼워 검증한다.
"""

from datetime import UTC, datetime
from typing import Any

import pytest
from httpx import ASGITransport, AsyncClient

from app.api.auth import get_current_account
from app.db.models.company import Company
from app.db.session import get_session
from main import app


class FakeAuthSession:
    """auth_service.signup 이 쓰는 scalar / add / commit / refresh 만 흉내낸다."""

    def __init__(self) -> None:
        self.rows: dict[int, Company] = {}
        self._next_id = 1

    async def scalar(self, stmt: Any) -> Company | None:
        # select(Company).where(Company.email == <값>) 에서 이메일 리터럴을 꺼낸다.
        email = stmt._where_criteria[0].right.value
        return next((c for c in self.rows.values() if c.email == email), None)

    def add(self, entity: Company) -> None:
        if entity.id is None:
            entity.id = self._next_id
            self._next_id += 1
        self.rows[entity.id] = entity

    async def commit(self) -> None:
        pass

    async def refresh(self, entity: Company) -> None:
        # 실제 세션은 server_default 컬럼(created_at)을 다시 읽어온다.
        if entity.created_at is None:
            entity.created_at = datetime.now(UTC)


@pytest.fixture
async def auth_api_client():
    fake = FakeAuthSession()

    async def override_session():
        yield fake

    app.dependency_overrides[get_session] = override_session
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as c:
        yield c, fake
    app.dependency_overrides.clear()


SIGNUP_BODY = {
    "email": "a@agentdo.io",
    "password": "password123",
    "name": "에이전트두",
    "contact_name": "김준혁",
}


async def test_회원가입시_회사정보가_저장된다(auth_api_client):
    client, fake = auth_api_client
    response = await client.post("/auth/signup", json=SIGNUP_BODY)

    assert response.status_code == 200
    data = response.json()["data"]
    assert data["email"] == "a@agentdo.io"
    assert data["name"] == "에이전트두"
    assert data["contact_name"] == "김준혁"
    assert data["has_profile"] is False

    saved = fake.rows[data["id"]]
    assert saved.name == "에이전트두"
    assert saved.contact_name == "김준혁"
    assert saved.hashed_password != "password123"  # 평문 저장 금지


async def test_회사정보는_선택값이다(auth_api_client):
    client, _ = auth_api_client
    response = await client.post(
        "/auth/signup", json={"email": "b@agentdo.io", "password": "password123"}
    )
    assert response.status_code == 200
    data = response.json()["data"]
    assert data["name"] is None
    assert data["contact_name"] is None


async def test_중복_이메일은_409(auth_api_client):
    client, _ = auth_api_client
    await client.post("/auth/signup", json=SIGNUP_BODY)
    response = await client.post("/auth/signup", json=SIGNUP_BODY)
    assert response.status_code == 409


async def test_토큰_없이_로그아웃하면_401(auth_api_client):
    client, _ = auth_api_client
    response = await client.post("/auth/logout")
    assert response.status_code == 401
    assert response.json()["success"] is False


async def test_로그인한_상태에서_로그아웃하면_200(auth_api_client):
    client, _ = auth_api_client
    app.dependency_overrides[get_current_account] = lambda: Company(
        id=1, email="a@agentdo.io"
    )
    response = await client.post("/auth/logout")
    assert response.status_code == 200
    assert response.json()["success"] is True
