import asyncio
from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import inspect
from sqlalchemy.ext.asyncio import create_async_engine
from testcontainers.postgres import PostgresContainer

from app.config import get_settings

ALEMBIC_INI = Path(__file__).resolve().parents[1] / "alembic.ini"


def test_alembic_upgrade_head_creates_error_codes_table(monkeypatch):
    # 실제 운영 경로(alembic upgrade head)를 신선한 DB에 대해 그대로 실행해서
    # 검증한다. tests/test_error_code_model.py는 create_all()로 만든 스키마만
    # 검증하므로, 이 테스트가 실제 마이그레이션 파일 자체의 정상 동작을 보장한다.
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
                        insp = inspect(sync_conn)
                        tables = insp.get_table_names()
                        columns = {c["name"] for c in insp.get_columns("error_codes")}
                        return tables, columns

                    return await conn.run_sync(_read)
            finally:
                await engine.dispose()

        tables, columns = asyncio.run(_inspect())

    assert "error_codes" in tables
    assert {
        "id", "created_at", "updated_at", "created_by", "updated_by",
        "code", "message", "http_status", "is_default", "is_active",
    } <= columns
