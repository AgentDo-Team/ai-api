from fastapi import FastAPI

app = FastAPI(title="ai-api")


@app.get("/")
def read_root():
    return {"message": "Hello from ai-api!"}


@app.get("/health")
def health_check():
    return {"status": "ok"}


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
