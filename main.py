from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.api.auth import router as auth_router
from app.api.profile import router as profile_router
from app.common.exception_handlers import register_exception_handlers
from app.schemas.response import ApiResponse



app = FastAPI(title="ai-api")
register_exception_handlers(app)
app.include_router(auth_router)
app.include_router(profile_router)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],  # 프론트 주소
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/")
def read_root() -> ApiResponse[dict]:
    return ApiResponse.ok(data={"message": "Hello from ai-api!"})


@app.get("/health")
def health_check() -> ApiResponse[dict]:
    return ApiResponse.ok(data={"status": "ok"}, message="정상 동작 중입니다.")


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
