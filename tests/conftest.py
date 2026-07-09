import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from sqlmodel import SQLModel
from testcontainers.postgres import PostgresContainer

import app.models  # noqa: F401  (모든 모델을 metadata에 등록)
from app.db import make_engine


@pytest.fixture(scope="session")
def pg_url() -> str:
    with PostgresContainer("postgres:16", driver="asyncpg") as pg:
        yield pg.get_connection_url()


@pytest_asyncio.fixture(scope="session")
async def db_engine(pg_url):
    engine = make_engine(pg_url)
    async with engine.begin() as conn:
        await conn.run_sync(SQLModel.metadata.create_all)
    yield engine
    await engine.dispose()


@pytest_asyncio.fixture
async def db_session(db_engine) -> AsyncSession:
    # 외부 커넥션 트랜잭션 + SAVEPOINT 조인 패턴으로 테스트 격리를 보장한다.
    # 테스트 코드가 session.commit()을 호출해도 SAVEPOINT만 커밋되므로,
    # 여기서 바깥 트랜잭션을 rollback하면 이번 테스트의 모든 변경이 사라진다.
    connection = await db_engine.connect()
    trans = await connection.begin()
    maker = async_sessionmaker(
        bind=connection, expire_on_commit=False, join_transaction_mode="create_savepoint"
    )
    async with maker() as session:
        yield session
    await trans.rollback()
    await connection.close()
