"""/api/companies/{id}/projects 엔드포인트 단위 테스트."""

PROJECT_BODY = {
    "title": "육군 통합 물자관리 시스템 고도화",
    "client": "국방부",
    "domain": "국방",
    "tech_stack": "Python, FastAPI",
    "develop_features": "재고 예측",
    "content": "물자관리 전 과정 재설계",
    "performance": "처리 속도 40% 개선",
}


async def test_create_project_does_not_embed(client, company, project_repo):
    """CRUD 는 임베딩하지 않는다. embedding 컬럼은 NULL(=미임베딩) 로 남는다."""
    response = await client.post(
        f"/api/companies/{company['id']}/projects", json=PROJECT_BODY
    )

    assert response.status_code == 201
    data = response.json()["data"]
    assert data["company_id"] == company["id"]
    assert data["title"] == "육군 통합 물자관리 시스템 고도화"
    assert data["embedded"] is False
    assert "embedding" not in data

    assert project_repo.rows[data["id"]].embedding is None


async def test_create_project_without_title_returns_422(client, company):
    response = await client.post(
        f"/api/companies/{company['id']}/projects", json={"client": "국방부"}
    )

    assert response.status_code == 422


async def test_create_project_for_missing_company_returns_404(client):
    response = await client.post("/api/companies/999/projects", json=PROJECT_BODY)

    assert response.status_code == 404
    assert response.json()["message"] == "회사를 찾을 수 없습니다."


async def test_list_projects_returns_only_that_companys_projects(
    client, company, other_company
):
    other_id = other_company["id"]

    await client.post(f"/api/companies/{company['id']}/projects", json=PROJECT_BODY)
    await client.post(
        f"/api/companies/{company['id']}/projects", json={**PROJECT_BODY, "title": "두번째"}
    )
    await client.post(
        f"/api/companies/{other_id}/projects", json={**PROJECT_BODY, "title": "남의것"}
    )

    response = await client.get(f"/api/companies/{company['id']}/projects")

    assert response.status_code == 200
    titles = [p["title"] for p in response.json()["data"]]
    assert titles == ["육군 통합 물자관리 시스템 고도화", "두번째"]


async def test_list_projects_paginates(client, company):
    for i in range(3):
        await client.post(
            f"/api/companies/{company['id']}/projects",
            json={**PROJECT_BODY, "title": f"P{i}"},
        )

    response = await client.get(
        f"/api/companies/{company['id']}/projects", params={"limit": 2, "offset": 1}
    )

    assert [p["title"] for p in response.json()["data"]] == ["P1", "P2"]


async def test_get_project(client, company):
    created = await client.post(
        f"/api/companies/{company['id']}/projects", json=PROJECT_BODY
    )
    project_id = created.json()["data"]["id"]

    response = await client.get(f"/api/companies/{company['id']}/projects/{project_id}")

    assert response.status_code == 200
    assert response.json()["data"]["client"] == "국방부"


async def test_get_project_of_another_company_returns_404(
    client, company, other_company
):
    created = await client.post(
        f"/api/companies/{company['id']}/projects", json=PROJECT_BODY
    )
    project_id = created.json()["data"]["id"]

    response = await client.get(
        f"/api/companies/{other_company['id']}/projects/{project_id}"
    )

    assert response.status_code == 404
    assert response.json()["message"] == "프로젝트를 찾을 수 없습니다."


async def test_get_missing_project_returns_404(client, company):
    response = await client.get(f"/api/companies/{company['id']}/projects/999")

    assert response.status_code == 404


async def test_update_project_only_changes_sent_fields(client, company, project_repo):
    created = await client.post(
        f"/api/companies/{company['id']}/projects", json=PROJECT_BODY
    )
    project_id = created.json()["data"]["id"]

    response = await client.patch(
        f"/api/companies/{company['id']}/projects/{project_id}",
        json={"performance": "처리 속도 60% 개선"},
    )

    assert response.status_code == 200
    data = response.json()["data"]
    assert data["performance"] == "처리 속도 60% 개선"
    assert data["client"] == "국방부"  # 안 보낸 필드는 유지
    assert data["embedded"] is False
    assert project_repo.rows[project_id].embedding is None


async def test_update_project_of_another_company_returns_404(
    client, company, other_company
):
    created = await client.post(
        f"/api/companies/{company['id']}/projects", json=PROJECT_BODY
    )
    project_id = created.json()["data"]["id"]

    response = await client.patch(
        f"/api/companies/{other_company['id']}/projects/{project_id}",
        json={"title": "탈취"},
    )

    assert response.status_code == 404


async def test_delete_project(client, company):
    created = await client.post(
        f"/api/companies/{company['id']}/projects", json=PROJECT_BODY
    )
    project_id = created.json()["data"]["id"]

    response = await client.delete(
        f"/api/companies/{company['id']}/projects/{project_id}"
    )

    assert response.status_code == 200
    assert (
        await client.get(f"/api/companies/{company['id']}/projects/{project_id}")
    ).status_code == 404


async def test_delete_missing_project_returns_404(client, company):
    response = await client.delete(f"/api/companies/{company['id']}/projects/999")

    assert response.status_code == 404
