from app.db import raw_connection
from app.queries import queries
from app.runtime_settings import (
    get_runtime_settings,
    invalidate_runtime_settings,
)
from app.utils.time import now_local


async def _put(db_session, key: str, value: str) -> None:
    conn = await raw_connection(db_session)
    now = now_local()
    await queries.upsert_setting(
        conn, key=key, value=value, now=now, actor_id=None
    )
    invalidate_runtime_settings()


async def test_empty_table_yields_env_defaults(db_session):
    conn = await raw_connection(db_session)
    rs = await get_runtime_settings(conn)
    assert rs.render_font_size == 30
    assert rs.script_provider == "fake"


async def test_override_row_wins(db_session):
    await _put(db_session, "render_font_size", "48")
    conn = await raw_connection(db_session)
    rs = await get_runtime_settings(conn)
    assert rs.render_font_size == 48


async def test_upsert_replaces_existing_value(db_session):
    await _put(db_session, "render_font_size", "48")
    await _put(db_session, "render_font_size", "64")

    conn = await raw_connection(db_session)
    # select_all_settings는 suffix 없는 "여러 행" 쿼리라 asyncpg 드라이버에서
    # 비동기 제너레이터로 온다 — await가 아니라 async for로 소비한다.
    rows = [r async for r in queries.select_all_settings(conn)]
    matching = [r for r in rows if r["key"] == "render_font_size"]
    assert len(matching) == 1
    assert (await get_runtime_settings(conn)).render_font_size == 64


async def test_delete_setting_restores_default(db_session):
    await _put(db_session, "render_font_size", "48")
    conn = await raw_connection(db_session)
    await queries.delete_setting(conn, key="render_font_size")
    invalidate_runtime_settings()

    assert (await get_runtime_settings(conn)).render_font_size == 30


async def test_cache_serves_repeated_reads(db_session):
    """두 번째 호출은 DB를 다시 읽지 않는다 — 무효화 전까지 같은 인스턴스다."""
    conn = await raw_connection(db_session)
    first = await get_runtime_settings(conn)
    second = await get_runtime_settings(conn)
    assert first is second


async def test_invalidate_forces_reload(db_session):
    conn = await raw_connection(db_session)
    first = await get_runtime_settings(conn)
    invalidate_runtime_settings()
    second = await get_runtime_settings(conn)
    assert first is not second


async def test_db_failure_falls_back_to_defaults_without_raising(db_session, monkeypatch):
    """설정 테이블 장애가 파이프라인 전체를 멈추게 하지 않는다."""
    async def _boom(*args, **kwargs):
        raise RuntimeError("relation does not exist")

    monkeypatch.setattr(queries, "select_all_settings", _boom)
    conn = await raw_connection(db_session)
    rs = await get_runtime_settings(conn)
    assert rs.render_font_size == 30
