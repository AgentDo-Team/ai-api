from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlmodel import SQLModel

from app.api.auth import router as auth_router
from app.api.profile import router as profile_router
from app.api.search import router as search_router
from app.common.exception_handlers import register_exception_handlers
from app.schemas.response import ApiResponse
from app.api import bids, companies, company_profiles, company_projects, ingest, third_filter

OPENAPI_TAGS = [
    {
        "name": "companies",
        "description": "회사 기본 정보 CRUD. 프로필·프로젝트의 상위 리소스이며, 삭제 시 하위 리소스도 함께 삭제된다.",
    },
    {
        "name": "company-profiles",
        "description": (
            "회사 프로필 CRUD (회사당 1건). 주력기술·보유솔루션·강점 등 회사의 성격을 나타내는 정보를 "
            "저장한다."
        ),
    },
    {
        "name": "company-projects",
        "description": (
            "회사 수행 프로젝트(실적) CRUD (회사당 N건). 이후 입찰공고와의 유사도 검색에 사용된다."
        ),
    },
    {
        "name": "third-filter",
        "description": (
            "3차 필터. 2차 필터 결과를 받아 평가기준표 기반 채점 후, 최종점수 상위 5건에 대해 "
            "LLM 적합/부적합 검증과 100자 공고 요약을 수행한다."
        ),
        
    },
    {
        "name": "bid-notices",
        "description": "공고 검색. 정형 조건 하드 필터링으로 공고를 추출하고 검색 세션(채팅방)을 저장한다."
    },    
    {
        "name": "system", 
        "description": "헬스체크 등 시스템 엔드포인트."
    }
]

DESCRIPTION = """
AI 입찰공고 분석 서비스 API.

**공통 응답 포맷** — 모든 응답은 `ApiResponse` 로 감싸진다.

```json
{ "success": true, "message": "요청이 성공적으로 처리되었습니다.", "data": { } }
```

실패 시 `success=false`, `message`에 사유가 담기고 `data`는 `null`이다(422 검증 실패만 `data`에 상세가 담긴다).

프로필·프로젝트 응답의 `embedded` 는 벡터 컬럼이 채워졌는지만 알려준다. 지금은 채우는 로직이 없어 항상 `false` 다.
"""

app = FastAPI(
    title="ai-api",
    version="0.1.0",
    description=DESCRIPTION,
    openapi_tags=OPENAPI_TAGS,
    # Swagger UI에서 Authorize로 넣은 토큰이 새로고침 후에도 유지되게 한다
    swagger_ui_parameters={"persistAuthorization": True},
)
register_exception_handlers(app)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],  # 프론트 주소
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth_router)
app.include_router(profile_router)
app.include_router(companies.router)
app.include_router(company_profiles.router)
app.include_router(company_projects.router)
app.include_router(third_filter.router)
app.include_router(bids.router)
app.include_router(ingest.router)
app.include_router(search_router)


@app.get("/", tags=["system"], summary="루트")
def read_root() -> ApiResponse[dict]:
    return ApiResponse.ok(data={"message": "Hello from ai-api!"})


@app.get("/health", tags=["system"], summary="헬스체크")
def health_check() -> ApiResponse[dict]:
    return ApiResponse.ok(data={"status": "ok"}, message="정상 동작 중입니다.")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
