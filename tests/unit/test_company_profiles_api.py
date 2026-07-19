"""/api/companies/{id}/profile 엔드포인트 단위 테스트."""

PROFILE_BODY = {
    "company_scale": "SMALL",
    "target_techs": "AI, RAG",
    "offered_solutions": "입찰공고 분석 SaaS",
    "strengths_diff": "국방 도메인 경험 다수",
    "credit_rating": "A+",
    "sp_grade": "1",
}


async def test_create_profile_does_not_embed(client, company, profile_repo):
    """CRUD 는 임베딩하지 않는다. embedding 컬럼은 NULL(=미임베딩) 로 남는다."""
    response = await client.post(
        f"/api/companies/{company['id']}/profile", json=PROFILE_BODY
    )

    assert response.status_code == 201
    data = response.json()["data"]
    assert data["company_id"] == company["id"]
    assert data["target_techs"] == "AI, RAG"
    assert data["embedded"] is False
    assert "embedding" not in data  # 1024 float 를 응답에 싣지 않는다

    assert profile_repo.rows[data["id"]].embedding is None


async def test_create_second_profile_returns_409(client, company):
    await client.post(f"/api/companies/{company['id']}/profile", json=PROFILE_BODY)

    response = await client.post(
        f"/api/companies/{company['id']}/profile", json=PROFILE_BODY
    )

    assert response.status_code == 409
    assert "이미 프로필이 존재합니다" in response.json()["message"]


async def test_create_profile_for_missing_company_returns_404(client):
    response = await client.post("/api/companies/999/profile", json=PROFILE_BODY)

    assert response.status_code == 404
    assert response.json()["message"] == "회사를 찾을 수 없습니다."


async def test_get_profile(client, company):
    await client.post(f"/api/companies/{company['id']}/profile", json=PROFILE_BODY)

    response = await client.get(f"/api/companies/{company['id']}/profile")

    assert response.status_code == 200
    assert response.json()["data"]["target_techs"] == "AI, RAG"


async def test_get_missing_profile_returns_404(client, company):
    response = await client.get(f"/api/companies/{company['id']}/profile")

    assert response.status_code == 404
    assert response.json()["message"] == "회사 프로필을 찾을 수 없습니다."


async def test_update_profile_only_changes_sent_fields(client, company, profile_repo):
    created = await client.post(
        f"/api/companies/{company['id']}/profile", json=PROFILE_BODY
    )
    profile_id = created.json()["data"]["id"]

    response = await client.patch(
        f"/api/companies/{company['id']}/profile",
        json={"target_techs": "AI, RAG, MCP"},
    )

    assert response.status_code == 200
    data = response.json()["data"]
    assert data["target_techs"] == "AI, RAG, MCP"
    assert data["credit_rating"] == "A+"  # 안 보낸 필드는 유지
    assert data["embedded"] is False
    assert profile_repo.rows[profile_id].embedding is None


async def test_update_profile_refreshes_row_after_commit(client, company, session):
    """updated_at 은 onupdate=now() 라 UPDATE 후 refresh 하지 않으면 응답 직렬화 중
    lazy load 가 걸려 실제 DB에서 MissingGreenlet(500)이 난다."""
    await client.post(f"/api/companies/{company['id']}/profile", json=PROFILE_BODY)
    refreshes_after_create = len(session.refreshed)

    response = await client.patch(
        f"/api/companies/{company['id']}/profile", json={"credit_rating": "AA0"}
    )

    assert response.status_code == 200
    assert len(session.refreshed) == refreshes_after_create + 1


async def test_update_profile_invalidates_existing_embedding(
    client, company, profile_repo
):
    created = await client.post(
        f"/api/companies/{company['id']}/profile", json=PROFILE_BODY
    )
    profile = profile_repo.rows[created.json()["data"]["id"]]
    profile.embedding = [0.1, 0.2]

    response = await client.patch(
        f"/api/companies/{company['id']}/profile",
        json={"target_techs": "AI, RAG, MCP"},
    )

    assert response.status_code == 200
    assert profile.embedding is None
    assert response.json()["data"]["embedded"] is False


async def test_update_missing_profile_returns_404(client, company):
    response = await client.patch(
        f"/api/companies/{company['id']}/profile", json={"target_techs": "x"}
    )

    assert response.status_code == 404


async def test_delete_profile(client, company):
    await client.post(f"/api/companies/{company['id']}/profile", json=PROFILE_BODY)

    response = await client.delete(f"/api/companies/{company['id']}/profile")

    assert response.status_code == 200
    assert (
        await client.get(f"/api/companies/{company['id']}/profile")
    ).status_code == 404
