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
    from app.core import cleanup, error_log, events, worker

    events.reset()
    worker.reset()
    cleanup.reset()
    _deny_error_log_db(error_log)
    yield
    events.reset()
    worker.reset()
    cleanup.reset()
    _deny_error_log_db(error_log)


def _deny_error_log_db(error_log) -> None:
    """record_error가 실제 DB에 쓰지 못하게 막는다.

    error_log.reset()으로 되돌리면 기본값이 app.db.async_session_maker —
    개발자의 진짜 DB(.env의 DATABASE_URL)에 붙은 팩토리다. 500을 유발하는 테스트는
    error_sink를 요청하지 않아도 500 핸들러를 타므로, 그대로 두면 스위트가 실 DB의
    error_logs를 오염시킨다(실제로 test_health.py가 그랬다).

    거부용 팩토리를 심어 두면 그런 테스트는 record_error의 정상 경로("삼키고
    warning")를 탈 뿐이고, 기록을 검증해야 하는 테스트만 error_sink로 옵트인한다.
    """
    from contextlib import asynccontextmanager

    @asynccontextmanager
    async def _no_db():
        raise RuntimeError("테스트가 error_sink 없이 record_error를 탔다")
        yield  # pragma: no cover

    error_log.set_session_factory(_no_db)


@pytest.fixture(autouse=True)
def reset_runtime_settings():
    # 런타임 설정 캐시도 프로세스 전역이다. 앞 테스트가 넣은 오버라이드가
    # 롤백된 뒤에도 캐시에 남아 다음 테스트를 오염시키는 것을 막는다.
    from app.runtime_settings import invalidate_runtime_settings

    invalidate_runtime_settings()
    yield
    invalidate_runtime_settings()


@pytest.fixture(autouse=True)
def deny_real_smtp(tmp_path, monkeypatch):
    """스위트가 진짜 메일을 보내지 못하게 막는다.

    SMTP_HOST가 비면 send_email이 파일 폴백을 타므로 실제 발송이 구조적으로
    불가능해진다. autouse인 이유는 _deny_error_log_db와 같다 — 보호를 옵트인으로
    두면 발송 경로를 타는 테스트가 그걸 요청하는 걸 잊는 순간 개발자 .env의 SMTP
    계정으로 진짜 메일이 나간다. 실제로 그랬다: request 엔드포인트 테스트 3개가
    mail_env를 받지 않아, 스위트를 한 번 돌릴 때마다 smtp.gmail.com에 접속해
    존재하지 않는 @example.com 주소로 발송을 시도했다.

    SMTP가 설정된 상태를 검증해야 하는 테스트는 자기 픽스처에서 다시 세팅한다
    (mail_env·test_email.py의 smtp_calls). autouse가 먼저 돌므로 그쪽이 이긴다.

    LOG_DIR도 함께 돌린다. SMTP를 끄면 발송이 .eml 파일 폴백을 타는데, 그대로
    두면 진짜 메일 대신 개발자의 실제 로그 디렉토리에 .eml이 쌓인다 — 실제로
    26개가 그렇게 쌓여 있었다. 오염 경로를 메일에서 파일로 옮기기만 하는 셈이라
    여기서 같이 막는다.
    """
    monkeypatch.setenv("SMTP_HOST", "")
    monkeypatch.setenv("LOG_DIR", str(tmp_path))
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


@pytest.fixture
def mail_env(tmp_path, monkeypatch):
    """메일을 파일로 떨구는 개발 모드로 고정하고, 그 출력 디렉토리를 준다.

    LOG_DIR을 tmp_path로 돌려 테스트가 실제 log/ 디렉토리를 더럽히지 않게 하고,
    SMTP_HOST를 비워 로컬 .env에 SMTP 설정이 있어도 진짜 메일이 나가지 않게 한다.
    get_settings는 lru_cache라 env를 바꾼 뒤 캐시를 비워야 반영된다.
    """
    monkeypatch.setenv("LOG_DIR", str(tmp_path))
    monkeypatch.setenv("SMTP_HOST", "")
    # 발신자도 비워 둔다 — 로컬 .env에 SMTP_FROM이 있으면 폴백 테스트가 흔들린다.
    monkeypatch.setenv("SMTP_USER", "")
    monkeypatch.setenv("SMTP_FROM", "")
    get_settings.cache_clear()
    yield tmp_path / "mail"
    get_settings.cache_clear()


@pytest.fixture
def error_sink(db_session):
    """record_error가 테스트 세션에 쓰게 한다.

    record_error는 기본적으로 app.db.async_session_maker(실제 DB 엔진에 붙은 팩토리)로
    자기 세션을 연다. 테스트에서 그대로 두면 SAVEPOINT 격리 밖으로 나가 개발자의 실제
    DB에 쓴다 — worker·cleanup이 session_factory를 주입받는 것과 같은 이유다.
    """
    from contextlib import asynccontextmanager

    from app.core import error_log

    @asynccontextmanager
    async def _make():
        yield db_session

    error_log.set_session_factory(_make)
    return db_session
