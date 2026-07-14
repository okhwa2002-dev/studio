import logging
from collections.abc import AsyncIterator

from sqlalchemy import event
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.config import get_settings

sql_logger = logging.getLogger("app.sql")


def _log_query(record) -> None:
    """asyncpg가 실행한 쿼리 하나를 로그로 남긴다 (LOG_SQL=true일 때만 등록된다).

    파라미터 값(record.args)은 **일부러 남기지 않는다.** 이 앱의 쿼리에는
    password_hash와 리프레시 토큰 해시가 파라미터로 들어오므로, 값을 찍으면
    인증 비밀이 그대로 로그 파일에 쌓인다. SQL문과 소요시간만으로 충분하다.
    """
    query = " ".join(record.query.split())  # .sql 파일의 여러 줄을 한 줄로
    elapsed_ms = record.elapsed * 1000

    if record.exception is not None:
        sql_logger.warning("SQL %.1fms FAILED %s (%s)", elapsed_ms, query, record.exception)
    else:
        sql_logger.info("SQL %.1fms %s", elapsed_ms, query)


def make_engine(url: str) -> AsyncEngine:
    engine = create_async_engine(url, echo=False, pool_pre_ping=True)

    if get_settings().log_sql:
        # 후크를 asyncpg 커넥션에 건다. SQLAlchemy도 결국 asyncpg 드라이버로
        # 나가므로, 여기 한 곳이면 aiosql 쿼리와 ORM 쿼리가 모두 잡힌다.
        # (SQLAlchemy의 echo=True는 aiosql이 raw 커넥션으로 보내는 쿼리를 못 본다.)
        @event.listens_for(engine.sync_engine, "connect")
        def _register_query_logger(dbapi_connection, connection_record) -> None:
            dbapi_connection.driver_connection.add_query_logger(_log_query)

    return engine


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
