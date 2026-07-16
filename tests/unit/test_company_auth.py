"""companies / company-profiles / company-projects 라우터의 JWT 인증(본인 회사 확인) 단위 테스트.

conftest 의 client fixture 는 verify_company_access 를 우회하므로,
여기서는 인증 의존성을 실제로 태우는 별도 클라이언트를 구성한다.
- 토큰 없음 → 401
- 토큰의 회사 id ≠ 경로의 company_id → 403
- 일치 → 통과 (이후 CRUD 로직으로 진행)
"""

import pytest
from httpx import ASGITransport, AsyncClient

from app.api.auth import get_current_account
from app.api.deps import get_company_service
from app.db.models.company import Company
from app.services.company_service import CompanyService
from main import app

PROJECT_BODY = {"title": "차세대 국방 정보체계 구축", "client": "국방부"}


@pytest.fixture
async def auth_client(session, company_repo, profile_repo, project_repo):
    """verify_company_access 를 우회하지 않는 클라이언트.

    get_current_account 만 갈아끼워 'id=1 회사로 로그인한 상태'를 흉내낸다.
    """
    service = CompanyService(
        session=session,
        company_repo=company_repo,
        profile_repo=profile_repo,
        project_repo=project_repo,
    )
    await company_repo.add(Company(id=1, name="에이전트두", email="a@agentdo.io"))
    await company_repo.add(Company(id=2, name="남의회사", email="b@other.io"))

    app.dependency_overrides[get_company_service] = lambda: service
    app.dependency_overrides[get_current_account] = lambda: Company(
        id=1, name="에이전트두", email="a@agentdo.io"
    )
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as c:
        yield c
    app.dependency_overrides.clear()


@pytest.fixture
async def anonymous_client(session, company_repo, profile_repo, project_repo):
    """토큰 없이 요청하는 클라이언트 (get_current_account 도 실제 코드를 태운다)."""
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


async def test_토큰_없이_프로필_조회하면_401(anonymous_client):
    response = await anonymous_client.get("/api/companies/1/profile")
    assert response.status_code == 401
    assert response.json()["success"] is False


async def test_토큰_없이_프로젝트_생성하면_401(anonymous_client):
    response = await anonymous_client.post(
        "/api/companies/1/projects", json=PROJECT_BODY
    )
    assert response.status_code == 401


async def test_다른_회사_프로필_접근하면_403(auth_client):
    response = await auth_client.get("/api/companies/2/profile")
    assert response.status_code == 403
    assert response.json()["success"] is False


async def test_다른_회사_프로젝트_접근하면_403(auth_client):
    response = await auth_client.post(
        "/api/companies/2/projects", json=PROJECT_BODY
    )
    assert response.status_code == 403


async def test_본인_회사_프로젝트는_생성_가능(auth_client):
    response = await auth_client.post(
        "/api/companies/1/projects", json=PROJECT_BODY
    )
    assert response.status_code == 201
    assert response.json()["data"]["company_id"] == 1


async def test_본인_회사_프로필_없으면_404(auth_client):
    """인증은 통과하고, 이후 CRUD 로직(404)으로 정상 진행되는지 확인."""
    response = await auth_client.get("/api/companies/1/profile")
    assert response.status_code == 404


async def test_토큰_없이_회사_단건_조회하면_401(anonymous_client):
    response = await anonymous_client.get("/api/companies/1")
    assert response.status_code == 401


async def test_다른_회사_조회하면_403(auth_client):
    response = await auth_client.get("/api/companies/2")
    assert response.status_code == 403


async def test_다른_회사_삭제하면_403(auth_client):
    response = await auth_client.delete("/api/companies/2")
    assert response.status_code == 403


async def test_본인_회사는_조회_가능(auth_client):
    response = await auth_client.get("/api/companies/1")
    assert response.status_code == 200
    assert response.json()["data"]["id"] == 1
