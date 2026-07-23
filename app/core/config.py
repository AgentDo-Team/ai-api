from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_env: str = "local"
    log_level: str = "INFO"

    database_url: str = "postgresql+asyncpg://postgres:postgres@localhost:5432/ai_api"

    db_echo: bool = False
    openai_api_key: str | None = None
    embedding_model: str = "text-embedding-3-small"
    embedding_dim: int = 1024

    secret_key: str = "change-me-in-production"
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 60

    openai_api_key: str = ""
    llm_model: str = "gpt-4o-mini"
    fit_judgment_model: str = "gpt-5.5"
    embedding_model: str = "text-embedding-3-small"
    embedding_dim: int = 1024

    tavily_api_key: str = ""
    tavily_max_results: int = 3

    gmail_client_secret_file: str = "client_secret.json"
    gmail_token_file: str = "gmail_token.json"
    gmail_sender_email: str = ""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

@lru_cache
def get_settings() -> Settings:
    return Settings()

settings = get_settings()