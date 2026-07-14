"""단위 테스트 공통 fixture.

DB(Postgres) 없이 전 엔드포인트를 검증한다.
리포지토리만 가짜로 갈아끼우고, 라우터·DTO·CompanyService 로직은 실제 코드를 그대로 태운다.
"""

from typing import Any

import pytest
from httpx import ASGITransport, AsyncClient

from app.api.deps import get_company_service
from app.db.models.company import Company, CompanyProfile, CompanyProject
from app.services.company_service import CompanyService
from main import app


# --------------------------------------------------------------------------- #
# Fakes
# --------------------------------------------------------------------------- #


class FakeSession:
    """서비스가 호출하는 commit / refresh 만 흉내낸다."""

    def __init__(self) -> None:
        self.commits = 0
        self.refreshed: list[Any] = []

    async def commit(self) -> None:
        self.commits += 1

    async def refresh(self, entity: Any) -> None:
        """실제 세션은 DB 계산 컬럼(updated_at)을 다시 읽어온다. 메모리 fake 는 기록만 한다."""
        self.refreshed.append(entity)


class _BaseFakeRepo:
    """dict 저장소 + 자동 증가 ID."""

    def __init__(self) -> None:
        self.rows: dict[int, Any] = {}
        self._next_id = 1

    async def add(self, entity: Any) -> Any:
        if entity.id is None:
            entity.id = self._next_id
            self._next_id += 1
        self.rows[entity.id] = entity
        return entity

    async def get(self, entity_id: int) -> Any | None:
        return self.rows.get(entity_id)

    async def delete(self, entity: Any) -> None:
        self.rows.pop(entity.id, None)


class FakeCompanyRepository(_BaseFakeRepo):
    async def get_by_email(self, email: str) -> Company | None:
        return next((c for c in self.rows.values() if c.email == email), None)

    async def list(self, limit: int = 20, offset: int = 0) -> list[Company]:
        ordered = sorted(self.rows.values(), key=lambda c: c.id)
        return ordered[offset : offset + limit]


class FakeCompanyProfileRepository(_BaseFakeRepo):
    async def get_by_company_id(self, company_id: int) -> CompanyProfile | None:
        return next(
            (p for p in self.rows.values() if p.company_id == company_id), None
        )


class FakeCompanyProjectRepository(_BaseFakeRepo):
    async def list_by_company(
        self, company_id: int, limit: int = 20, offset: int = 0
    ) -> list[CompanyProject]:
        ordered = sorted(
            (p for p in self.rows.values() if p.company_id == company_id),
            key=lambda p: p.id,
        )
        return ordered[offset : offset + limit]


# --------------------------------------------------------------------------- #
# Fixtures
# --------------------------------------------------------------------------- #


@pytest.fixture
def company_repo() -> FakeCompanyRepository:
    return FakeCompanyRepository()


@pytest.fixture
def profile_repo() -> FakeCompanyProfileRepository:
    return FakeCompanyProfileRepository()


@pytest.fixture
def project_repo() -> FakeCompanyProjectRepository:
    return FakeCompanyProjectRepository()


@pytest.fixture
def session() -> FakeSession:
    return FakeSession()


@pytest.fixture
async def client(session, company_repo, profile_repo, project_repo):
    service = CompanyService(
        session=session,
        company_repo=company_repo,
        profile_repo=profile_repo,
        project_repo=project_repo,
    )
    app.dependency_overrides[get_company_service] = lambda: service
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as c:
        yield c
    app.dependency_overrides.clear()


@pytest.fixture
async def company(client) -> dict:
    """대부분의 테스트가 상위 리소스로 회사 1건을 필요로 한다."""
    response = await client.post(
        "/api/companies",
        json={"name": "에이전트두", "contact_name": "김준혁", "email": "a@agentdo.io"},
    )
    assert response.status_code == 201
    return response.json()["data"]
