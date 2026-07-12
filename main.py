from fastapi import FastAPI

from app.common.exception_handlers import register_exception_handlers
from app.schemas.response import ApiResponse

app = FastAPI(title="ai-api")
register_exception_handlers(app)


@app.get("/")
def read_root() -> ApiResponse[dict]:
    return ApiResponse.ok(data={"message": "Hello from ai-api!"})


@app.get("/health")
def health_check() -> ApiResponse[dict]:
    return ApiResponse.ok(data={"status": "ok"}, message="정상 동작 중입니다.")


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
