from collections.abc import AsyncIterator

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.config import get_settings


def make_engine(url: str) -> AsyncEngine:
    return create_async_engine(url, echo=False, pool_pre_ping=True)


engine: AsyncEngine = make_engine(get_settings().database_url)
async_session_maker = async_sessionmaker(engine, expire_on_commit=False)


async def get_db() -> AsyncIterator[AsyncSession]:
    async with async_session_maker() as session:
        yield session


async def raw_connection(session: AsyncSession):
    """SQLAlchemy AsyncSession과 같은 트랜잭션을 공유하는 raw asyncpg 커넥션을 반환한다.

    aiosql로 작성한 이름 붙은 쿼리(app/queries/*.sql)를 실행할 때 사용한다.
    같은 커넥션/트랜잭션을 그대로 쓰므로, 세션의 커밋 전 변경사항도 보이고
    테스트의 SAVEPOINT 격리도 그대로 적용된다.
    """
    conn = await session.connection()
    pooled = await conn.get_raw_connection()
    return pooled.driver_connection
