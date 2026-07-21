import os

os.environ["SCRIPT_PROVIDER"] = "fake"  # 통합 테스트는 실제 LLM 호출 없이 fake로
os.environ["VOICE_PROVIDER"] = "fake"  # 통합 테스트는 실제 TTS 호출 없이 fake로
os.environ["CAPTIONS_PROVIDER"] = "fake"  # 통합 테스트는 실제 whisper 모델 없이 fake로
os.environ["RENDER_PROVIDER"] = "fake"  # 통합 테스트는 실제 ffmpeg 없이 fake로
os.environ["WHISPER_MODEL"] = "small"  # 로컬 .env 값에 테스트가 흔들리지 않게 고정

from app.config import get_settings  # noqa: E402

get_settings.cache_clear()  # 위 env가 반영되도록 lru_cache 초기화

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from sqlmodel import SQLModel
from testcontainers.postgres import PostgresContainer

import app.models  # noqa: F401  (모든 모델을 metadata에 등록)
from app.db import get_db, make_engine


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


@pytest_asyncio.fixture
async def client(db_session):
    async def _override_get_db():
        yield db_session

    from app.main import app

    app.dependency_overrides[get_db] = _override_get_db
    transport = ASGITransport(app=app, raise_app_exceptions=False)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c
    app.dependency_overrides.clear()
