"""회원가입 → has_profile 분기 → 자사 프로필 저장/조회 흐름 검증.

실제 PostgreSQL 스키마를 드롭 후 재생성하고(개발 DB), 실제 엔드포인트로 태운다.
"""

import asyncio
import uuid

from httpx import ASGITransport, AsyncClient
from sqlalchemy import text
from sqlmodel import SQLModel

import app.db.models  # noqa: F401  모든 모델을 metadata에 등록
import main
from app.db.session import engine


async def recreate_schema():
    async with engine.begin() as conn:
        await conn.execute(text("DROP SCHEMA public CASCADE"))
        await conn.execute(text("CREATE SCHEMA public"))
        await conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
        await conn.run_sync(SQLModel.metadata.create_all)


async def run():
    await recreate_schema()
    email = f"corp-{uuid.uuid4().hex[:8]}@example.com"
    transport = ASGITransport(app=main.app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        # 1) 회원가입
        r = await ac.post(
            "/auth/signup", json={"email": email, "password": "password123"}
        )
        print("[signup]", r.status_code, r.json())
        assert r.status_code == 200
        assert r.json()["data"]["has_profile"] is False

        # 2) 로그인 → 토큰
        r = await ac.post(
            "/auth/login", json={"email": email, "password": "password123"}
        )
        assert r.status_code == 200
        token = r.json()["data"]["access_token"]
        auth = {"Authorization": f"Bearer {token}"}

        # 3) 가입 직후 /auth/me → has_profile=False (온보딩 화면으로 분기되어야 함)
        r = await ac.get("/auth/me", headers=auth)
        print("[me before]", r.status_code, r.json())
        assert r.status_code == 200
        assert r.json()["data"]["has_profile"] is False

        # 4) 프로필 없을 때 GET /me/profile → data=null
        r = await ac.get("/me/profile", headers=auth)
        print("[profile before]", r.status_code, r.json())
        assert r.status_code == 200
        assert r.json()["data"] is None

        # 5) 자사 프로필 저장 (입력폼 제출)
        payload = {
            "company_scale": "중소기업",
            "target_techs": "에이전트 개발, 클라우드 전환, 디지털 전환",
            "offered_solutions": "자사 에이전트, AI 모델, RAG 기술",
            "strengths_diff": "온프레미스 RAG 구축 경험 다수",
            "credit_rating": "A",
            "sp_grade": "SP1",
        }
        r = await ac.put("/me/profile", json=payload, headers=auth)
        print("[profile save]", r.status_code, r.json())
        assert r.status_code == 200
        assert r.json()["data"]["sp_grade"] == "SP1"

        # 6) 저장 후 /auth/me → has_profile=True (채팅 화면으로 분기되어야 함)
        r = await ac.get("/auth/me", headers=auth)
        print("[me after]", r.status_code, r.json())
        assert r.json()["data"]["has_profile"] is True

        # 7) GET /me/profile → 저장한 값 반환
        r = await ac.get("/me/profile", headers=auth)
        print("[profile after]", r.status_code, r.json())
        assert r.json()["data"]["target_techs"] == payload["target_techs"]

        # 8) 프로필 갱신(upsert) — 같은 계정, 값 수정
        r = await ac.put(
            "/me/profile", json={**payload, "sp_grade": "SP2"}, headers=auth
        )
        assert r.json()["data"]["sp_grade"] == "SP2"
        # 여전히 프로필은 1개여야 함(중복 생성 X) → has_profile True 유지
        r = await ac.get("/auth/me", headers=auth)
        assert r.json()["data"]["has_profile"] is True

    await engine.dispose()
    print("\n✅ 분기(has_profile) + 프로필 저장/조회/갱신 모두 통과")


asyncio.run(run())
