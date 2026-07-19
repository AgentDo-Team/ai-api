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

    # LLM / 임베딩 설정 (OpenAI)
    # embedding_dim 은 DB의 Vector(1024) 컬럼과 반드시 일치해야 한다.
    openai_api_key: str = ""
    llm_model: str = "gpt-4o-mini"
    # 3차 필터의 공고↔회사 적합성 분석 전용 모델. 상위 5건에 대해서만 호출하는(=건수가 적은)
    # 대신 공고 전체를 통째로 읽고 추천사유/약점을 뽑는 무거운 판단이라 llm_model 과 분리한다.
    # 배점표 채점은 공고당 수십 회 호출이라 llm_model(저렴한 모델)을 그대로 쓴다.
    fit_judgment_model: str = "gpt-5.5"
    embedding_model: str = "text-embedding-3-small"
    embedding_dim: int = 1024

    # Tavily 웹 검색 API 키 (보완점 검색 에이전트에서 사용). .env 의 TAVILY_API_KEY 를 읽는다.
    tavily_api_key: str = ""
    # 검색어 1개당 Tavily 가 반환할 최대 결과 수 (0~20).
    tavily_max_results: int = 3

    # Gmail 발송 설정 (협업 제안 메일 에이전트에서 사용).
    # gmail_client_secret_file: Google Cloud Console 에서 발급한 OAuth 데스크톱 클라이언트 시크릿 json.
    # gmail_token_file: 최초 인증(app.clients.gmail_auth) 후 생성되는 access/refresh token json.
    # gmail_sender_email: 기본 발신자 주소(비우면 인증 계정의 기본 주소로 발송).
    gmail_client_secret_file: str = "client_secret.json"
    gmail_token_file: str = "gmail_token.json"
    gmail_sender_email: str = ""

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