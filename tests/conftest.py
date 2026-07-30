import os

os.environ["SCRIPT_PROVIDER"] = "fake"  # 통합 테스트는 실제 LLM 호출 없이 fake로
os.environ["VOICE_PROVIDER"] = "fake"  # 통합 테스트는 실제 TTS 호출 없이 fake로
os.environ["CAPTIONS_PROVIDER"] = "fake"  # 통합 테스트는 실제 whisper 모델 없이 fake로
os.environ["RENDER_PROVIDER"] = "fake"  # 통합 테스트는 실제 ffmpeg 없이 fake로
os.environ["WHISPER_MODEL"] = "small"  # 로컬 .env 값에 테스트가 흔들리지 않게 고정
os.environ["JWT_SECRET"] = "test-jwt-secret-that-is-32-bytes!"

# 아래 값들은 시스템 설정 테스트가 "기본값"으로 단언하는 값이다.
# 로컬 .env에 다른 값이 있어도 테스트가 흔들리지 않도록 여기서 못박는다.
os.environ["RENDER_BG_COLOR"] = "#0f172a"
os.environ["RENDER_FONT"] = "Malgun Gothic"
os.environ["RENDER_FONT_SIZE"] = "30"
os.environ["STOCK_SOURCES"] = '["pexels", "pixabay"]'   # 복합 타입은 JSON으로 준다
os.environ["STOCK_MAX_BYTES"] = "52428800"
os.environ["STOCK_TIMEOUT_SEC"] = "30"
os.environ["FAILED_LOGIN_LIMIT"] = "5"
os.environ["PASSWORD_MIN_LEN"] = "8"
os.environ["SIGNUP_AUTO_APPROVE"] = "false"

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


@pytest.fixture(autouse=True)
def reset_events():
    # 이벤트 버스·전역 워커 싱글턴은 프로세스 전역이라 테스트끼리 샌다. 앞뒤로 비운다.
    # worker.reset()이 없으면 get_worker().start()를 쓰는 테스트가 훗날 추가될 때
    # 앞선 테스트들이 module-global asyncio.Queue에 쌓아둔 stage id를 그대로 물려받는다.
    from app.core import cleanup, events, worker

    events.reset()
    worker.reset()
    cleanup.reset()
    yield
    events.reset()
    worker.reset()
    cleanup.reset()


@pytest.fixture(autouse=True)
def reset_runtime_settings():
    # 런타임 설정 캐시도 프로세스 전역이다. 앞 테스트가 넣은 오버라이드가
    # 롤백된 뒤에도 캐시에 남아 다음 테스트를 오염시키는 것을 막는다.
    from app.runtime_settings import invalidate_runtime_settings

    invalidate_runtime_settings()
    yield
    invalidate_runtime_settings()
