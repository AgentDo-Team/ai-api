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
