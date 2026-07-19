"""/api/companies/{id}/partners 엔드포인트 단위 테스트."""

PARTNER_BODY = {
    "name": "에이전트두 보안연구소",
    "domain": "정보보안",
    "tech_stack": "침해대응, 취약점진단, WAF",
    "description": "공공 SI 보안 관제 10년, 국방 도메인 인증 다수 보유",
}


async def test_create_partner(client, company, partner_repo):
    response = await client.post(
        f"/api/companies/{company['id']}/partners", json=PARTNER_BODY
    )

    assert response.status_code == 201
    data = response.json()["data"]
    assert data["company_id"] == company["id"]
    assert data["name"] == "에이전트두 보안연구소"
    assert data["domain"] == "정보보안"
    assert partner_repo.rows[data["id"]].tech_stack == "침해대응, 취약점진단, WAF"


async def test_create_partner_without_name_returns_422(client, company):
    response = await client.post(
        f"/api/companies/{company['id']}/partners", json={"domain": "정보보안"}
    )

    assert response.status_code == 422


async def test_create_partner_for_missing_company_returns_404(client):
    response = await client.post("/api/companies/999/partners", json=PARTNER_BODY)

    assert response.status_code == 404
    assert response.json()["message"] == "회사를 찾을 수 없습니다."


async def test_list_partners_returns_only_that_companys_partners(
    client, company, other_company
):
    other_id = other_company["id"]

    await client.post(f"/api/companies/{company['id']}/partners", json=PARTNER_BODY)
    await client.post(
        f"/api/companies/{company['id']}/partners", json={**PARTNER_BODY, "name": "두번째"}
    )
    await client.post(
        f"/api/companies/{other_id}/partners", json={**PARTNER_BODY, "name": "남의것"}
    )

    response = await client.get(f"/api/companies/{company['id']}/partners")

    assert response.status_code == 200
    names = [p["name"] for p in response.json()["data"]]
    assert names == ["에이전트두 보안연구소", "두번째"]


async def test_list_partners_paginates(client, company):
    for i in range(3):
        await client.post(
            f"/api/companies/{company['id']}/partners",
            json={**PARTNER_BODY, "name": f"P{i}"},
        )

    response = await client.get(
        f"/api/companies/{company['id']}/partners", params={"limit": 2, "offset": 1}
    )

    assert [p["name"] for p in response.json()["data"]] == ["P1", "P2"]


async def test_get_partner(client, company):
    created = await client.post(
        f"/api/companies/{company['id']}/partners", json=PARTNER_BODY
    )
    partner_id = created.json()["data"]["id"]

    response = await client.get(f"/api/companies/{company['id']}/partners/{partner_id}")

    assert response.status_code == 200
    assert response.json()["data"]["domain"] == "정보보안"


async def test_get_partner_of_another_company_returns_404(
    client, company, other_company
):
    created = await client.post(
        f"/api/companies/{company['id']}/partners", json=PARTNER_BODY
    )
    partner_id = created.json()["data"]["id"]

    response = await client.get(
        f"/api/companies/{other_company['id']}/partners/{partner_id}"
    )

    assert response.status_code == 404
    assert response.json()["message"] == "협력사를 찾을 수 없습니다."


async def test_get_missing_partner_returns_404(client, company):
    response = await client.get(f"/api/companies/{company['id']}/partners/999")

    assert response.status_code == 404


async def test_update_partner_only_changes_sent_fields(client, company, partner_repo):
    created = await client.post(
        f"/api/companies/{company['id']}/partners", json=PARTNER_BODY
    )
    partner_id = created.json()["data"]["id"]

    response = await client.patch(
        f"/api/companies/{company['id']}/partners/{partner_id}",
        json={"tech_stack": "클라우드 보안"},
    )

    assert response.status_code == 200
    data = response.json()["data"]
    assert data["tech_stack"] == "클라우드 보안"
    assert data["domain"] == "정보보안"  # 안 보낸 필드는 유지
    assert partner_repo.rows[partner_id].name == "에이전트두 보안연구소"


async def test_update_partner_of_another_company_returns_404(
    client, company, other_company
):
    created = await client.post(
        f"/api/companies/{company['id']}/partners", json=PARTNER_BODY
    )
    partner_id = created.json()["data"]["id"]

    response = await client.patch(
        f"/api/companies/{other_company['id']}/partners/{partner_id}",
        json={"name": "탈취"},
    )

    assert response.status_code == 404


async def test_delete_partner(client, company):
    created = await client.post(
        f"/api/companies/{company['id']}/partners", json=PARTNER_BODY
    )
    partner_id = created.json()["data"]["id"]

    response = await client.delete(
        f"/api/companies/{company['id']}/partners/{partner_id}"
    )

    assert response.status_code == 200
    assert (
        await client.get(f"/api/companies/{company['id']}/partners/{partner_id}")
    ).status_code == 404


async def test_delete_missing_partner_returns_404(client, company):
    response = await client.delete(f"/api/companies/{company['id']}/partners/999")

    assert response.status_code == 404
