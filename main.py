from fastapi import FastAPI

from app.api import companies, company_profiles, company_projects
from app.common.exception_handlers import register_exception_handlers
from app.schemas.response import ApiResponse

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
    {"name": "system", "description": "헬스체크 등 시스템 엔드포인트."},
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
)
register_exception_handlers(app)

app.include_router(companies.router)
app.include_router(company_profiles.router)
app.include_router(company_projects.router)


@app.get("/", tags=["system"], summary="루트")
def read_root() -> ApiResponse[dict]:
    return ApiResponse.ok(data={"message": "Hello from ai-api!"})


@app.get("/health", tags=["system"], summary="헬스체크")
def health_check() -> ApiResponse[dict]:
    return ApiResponse.ok(data={"status": "ok"}, message="정상 동작 중입니다.")


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
