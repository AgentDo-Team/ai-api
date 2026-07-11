from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlmodel.ext.asyncio.session import AsyncSession

from app.core.config import settings

# async 엔진 (asyncpg 드라이버)
engine = create_async_engine(
    settings.database_url,
    echo=settings.db_echo,
    pool_pre_ping=True,
)

async_session_factory = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


async def get_session() -> AsyncGenerator[AsyncSession, None]:
    """
    FastAPI 의존성 주입용 세션 제공자.
    요청이 올 때마다 세션을 하나 열어서(async with) 엔드포인트에 건네주고(yield), 
    엔드포인트가 다 쓰면 자동으로 닫아 커넥션을 반납하는, 비동기 세션 공급 함수
    """
    async with async_session_factory() as session:
        yield session
        
