import asyncio
from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import inspect
from sqlalchemy.ext.asyncio import create_async_engine
from testcontainers.postgres import PostgresContainer

from app.config import get_settings

ALEMBIC_INI = Path(__file__).resolve().parents[1] / "alembic.ini"


def test_alembic_upgrade_head_applies_cleanly_on_fresh_db(monkeypatch):
    # 실제 운영 경로(alembic upgrade head)를 신선한 DB에 대해 그대로 실행해서
    # 마이그레이션 체인 전체(생성/변경/삭제 이력 포함)가 에러 없이 끝까지
    # 적용되는지 검증한다. SQLModel의 create_all()과 달리 실제 마이그레이션
    # 파일 자체의 정상 동작을 보장하는 회귀 테스트다.
    with PostgresContainer("postgres:16") as pg:
        async_url = pg.get_connection_url(driver="asyncpg")
        monkeypatch.setenv("DATABASE_URL", async_url)
        get_settings.cache_clear()
        try:
            cfg = Config(str(ALEMBIC_INI))
            command.upgrade(cfg, "head")
        finally:
            get_settings.cache_clear()

        async def _inspect():
            engine = create_async_engine(async_url)
            try:
                async with engine.connect() as conn:
                    def _read(sync_conn):
                        return inspect(sync_conn).get_table_names()

                    return await conn.run_sync(_read)
            finally:
                await engine.dispose()

        tables = asyncio.run(_inspect())

    # error_codes는 이력상 생성된 뒤 삭제되었으므로(에러 처리가 소스 관리
    # 방식으로 바뀜) head에는 존재하지 않아야 한다.
    assert "error_codes" not in tables
    assert "users" in tables
    assert "refresh_tokens" in tables
    assert "alembic_version" in tables
