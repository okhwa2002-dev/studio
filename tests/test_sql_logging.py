import asyncio
import logging
import re

from app.config import Settings, get_settings
from app.db import make_engine

SQL_LOGGER = "app.sql"


async def _fetch_raw(engine, sql: str, *args):
    """raw asyncpg 커넥션으로 쿼리를 실행한다(aiosql이 쓰는 것과 같은 경로)."""
    async with engine.connect() as conn:
        pooled = await conn.get_raw_connection()
        raw = pooled.driver_connection
        result = await raw.fetchval(sql, *args)

    # asyncpg는 쿼리 로거 콜백을 loop.call_soon으로 다음 틱에 부른다.
    # 여기서 한 틱 양보하지 않으면 아직 로그가 남지 않은 상태로 단언하게 된다.
    await asyncio.sleep(0)
    return result


def _sql_messages(caplog) -> list[str]:
    return [r.getMessage() for r in caplog.records if r.name == SQL_LOGGER]


async def test_query_logging_is_off_when_disabled(pg_url, caplog, monkeypatch):
    # LOG_SQL을 명시적으로 끈다. 개발자의 로컬 .env가 켜져 있어도 이 테스트는
    # 같은 결과를 내야 한다(환경에 의존하는 테스트는 남의 머신에서 깨진다).
    monkeypatch.setenv("LOG_SQL", "false")
    get_settings.cache_clear()
    try:
        engine = make_engine(pg_url)
        with caplog.at_level(logging.INFO, logger=SQL_LOGGER):
            await _fetch_raw(engine, "SELECT 1")
        await engine.dispose()

        assert _sql_messages(caplog) == []
    finally:
        get_settings.cache_clear()


def test_log_sql_defaults_to_false():
    # _env_file=None으로 .env를 무시한 순수 기본값을 본다.
    # 운영에서 설정을 빼먹어도 쿼리 로그는 꺼져 있어야 한다.
    settings = Settings(_env_file=None, database_url="postgresql://x/y", jwt_secret="x")
    assert settings.log_sql is False


async def test_query_logging_records_sql_and_elapsed_when_enabled(pg_url, caplog, monkeypatch):
    monkeypatch.setenv("LOG_SQL", "true")
    get_settings.cache_clear()
    try:
        engine = make_engine(pg_url)
        with caplog.at_level(logging.INFO, logger=SQL_LOGGER):
            await _fetch_raw(engine, "SELECT 1")
        await engine.dispose()

        messages = _sql_messages(caplog)
        assert any("SELECT 1" in m for m in messages)
        # "SQL 2.4ms SELECT 1" 형태
        assert any(re.search(r"SQL \d+\.\dms", m) for m in messages)
    finally:
        get_settings.cache_clear()


async def test_query_logging_never_records_parameter_values(pg_url, caplog, monkeypatch):
    # 이 테스트가 이 기능의 안전장치다. 파라미터에는 password_hash와 리프레시 토큰
    # 해시가 그대로 들어오므로, 나중에 누군가 "디버깅 편하게" record.args를 로그에
    # 추가하면 인증 비밀이 로그 파일에 쌓인다. 그 변경을 여기서 막는다.
    secret = "super-secret-password-hash"
    monkeypatch.setenv("LOG_SQL", "true")
    get_settings.cache_clear()
    try:
        engine = make_engine(pg_url)
        with caplog.at_level(logging.INFO, logger=SQL_LOGGER):
            value = await _fetch_raw(engine, "SELECT $1::text", secret)
        await engine.dispose()

        assert value == secret  # 쿼리는 실제로 파라미터를 받아 실행됐다
        assert secret not in caplog.text  # 그런데 로그에는 값이 남지 않는다
        assert any("SELECT $1::text" in m for m in _sql_messages(caplog))
    finally:
        get_settings.cache_clear()
