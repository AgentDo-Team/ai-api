"""/api/companies 엔드포인트 단위 테스트.

회사 생성은 /auth/signup 이 담당하므로 (tests/unit/test_auth_api.py 참고)
여기서는 단건 조회/수정/삭제만 다룬다. 인증(401/403)은 test_company_auth.py 에서 검증한다.
"""

from app.db.models.company import Company


async def test_get_company(client, company):
    response = await client.get(f"/api/companies/{company['id']}")

    assert response.status_code == 200
    assert response.json()["data"]["name"] == "에이전트두"


async def test_get_missing_company_returns_404(client):
    response = await client.get("/api/companies/999")

    assert response.status_code == 404
    assert response.json()["message"] == "회사를 찾을 수 없습니다."


async def test_update_company_only_changes_sent_fields(client, company):
    response = await client.patch(
        f"/api/companies/{company['id']}", json={"contact_name": "이순신"}
    )

    assert response.status_code == 200
    data = response.json()["data"]
    assert data["contact_name"] == "이순신"
    assert data["name"] == "에이전트두"  # 안 보낸 필드는 유지
    assert data["email"] == "a@agentdo.io"


async def test_update_company_to_existing_email_returns_409(
    client, company, company_repo
):
    other = Company(
        name="다른회사", email="b@agentdo.io", hashed_password="fake-hash"
    )
    await company_repo.add(other)

    response = await client.patch(
        f"/api/companies/{other.id}", json={"email": company["email"]}
    )

    assert response.status_code == 409


async def test_update_company_keeping_own_email_succeeds(client, company):
    response = await client.patch(
        f"/api/companies/{company['id']}",
        json={"name": "새이름", "email": company["email"]},
    )

    assert response.status_code == 200
    assert response.json()["data"]["name"] == "새이름"


async def test_update_missing_company_returns_404(client):
    response = await client.patch("/api/companies/999", json={"name": "x"})

    assert response.status_code == 404


async def test_delete_company(client, company):
    response = await client.delete(f"/api/companies/{company['id']}")

    assert response.status_code == 200
    assert response.json()["message"] == "회사가 삭제되었습니다."

    assert (await client.get(f"/api/companies/{company['id']}")).status_code == 404


async def test_delete_missing_company_returns_404(client):
    response = await client.delete("/api/companies/999")

    assert response.status_code == 404
