"""/api/companies 엔드포인트 단위 테스트."""


async def test_create_company_returns_201_and_api_response_shape(client):
    response = await client.post(
        "/api/companies",
        json={"name": "에이전트두", "contact_name": "김준혁", "email": "a@agentdo.io"},
    )

    assert response.status_code == 201
    body = response.json()
    assert body["success"] is True
    assert body["message"] == "회사가 등록되었습니다."
    assert body["data"]["id"] == 1
    assert body["data"]["name"] == "에이전트두"
    assert body["data"]["email"] == "a@agentdo.io"


async def test_create_company_with_duplicate_email_returns_409(client, company):
    response = await client.post(
        "/api/companies", json={"name": "다른회사", "email": company["email"]}
    )

    assert response.status_code == 409
    body = response.json()
    assert body["success"] is False
    assert body["message"] == "이미 등록된 이메일입니다."
    assert body["data"] is None


async def test_create_company_with_invalid_email_returns_422(client):
    response = await client.post(
        "/api/companies", json={"name": "회사", "email": "not-an-email"}
    )

    assert response.status_code == 422
    assert response.json()["success"] is False


async def test_create_company_without_name_returns_422(client):
    response = await client.post("/api/companies", json={"contact_name": "김준혁"})

    assert response.status_code == 422


async def test_get_company(client, company):
    response = await client.get(f"/api/companies/{company['id']}")

    assert response.status_code == 200
    assert response.json()["data"]["name"] == "에이전트두"


async def test_get_missing_company_returns_404(client):
    response = await client.get("/api/companies/999")

    assert response.status_code == 404
    assert response.json()["message"] == "회사를 찾을 수 없습니다."


async def test_list_companies_paginates(client):
    for i in range(3):
        await client.post(
            "/api/companies", json={"name": f"회사{i}", "email": f"c{i}@x.io"}
        )

    response = await client.get("/api/companies", params={"limit": 2, "offset": 1})

    assert response.status_code == 200
    data = response.json()["data"]
    assert [c["name"] for c in data] == ["회사1", "회사2"]


async def test_update_company_only_changes_sent_fields(client, company):
    response = await client.patch(
        f"/api/companies/{company['id']}", json={"contact_name": "이순신"}
    )

    assert response.status_code == 200
    data = response.json()["data"]
    assert data["contact_name"] == "이순신"
    assert data["name"] == "에이전트두"  # 안 보낸 필드는 유지
    assert data["email"] == "a@agentdo.io"


async def test_update_company_to_existing_email_returns_409(client, company):
    other = await client.post(
        "/api/companies", json={"name": "다른회사", "email": "b@agentdo.io"}
    )
    other_id = other.json()["data"]["id"]

    response = await client.patch(
        f"/api/companies/{other_id}", json={"email": company["email"]}
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
