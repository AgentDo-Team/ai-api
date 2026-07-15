from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """
    애플리케이션 환경설정 (.env 로드).
    pydantic_settings.BaseSettings를 상속하면, 선언한 필드 이름과 같은 환경변수를 자동으로 찾아서 채워줍니다. 
    예를 들어 database_url 필드는 .env의 DATABASE_URL 값을 읽어옵니다 (대소문자 무시).

    우선순위: 실제 환경변수 > .env 파일 > 코드에 적은 기본값
    """

    app_env: str = "local"
    log_level: str = "INFO"

    # PostgreSQL + pgvector 접속 URL (async 드라이버 asyncpg 사용)
    database_url: str = "postgresql+asyncpg://postgres:postgres@localhost:5432/ai_api"

    # SQL 로그 출력 여부
    db_echo: bool = False

    # 임베딩 설정 (OpenAI text-embedding-3-small, dense 1024차원)
    # 렉시컬(정확 용어) 매칭은 chunks.content BM25(pg_search)가 담당하므로 dense만 쓴다.
    # openai_api_key는 비워두면 OpenAI SDK가 OPENAI_API_KEY 환경변수를 자동으로 읽는다.
    openai_api_key: str | None = None
    embedding_model: str = "text-embedding-3-small"
    embedding_dim: int = 1024

    # JWT 인증 설정
    # secret_key: JWT 서명용 비밀키. 운영 환경에서는 반드시 .env로 덮어쓸 것 (유출 금지)
    secret_key: str = "change-me-in-production"
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 60

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

# 세팅 내용을 한 번만 만들고 재사용하는거래
@lru_cache
def get_settings() -> Settings:
    return Settings()

# 다른 파일에서 from app.core.config import settings 으로 가져다 쓸 수 있다
settings = get_settings()