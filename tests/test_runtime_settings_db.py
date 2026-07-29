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


async def test_invalidate_during_fetch_does_not_cache_stale_value(db_session, monkeypatch):
    """DB 조회 중(await로 양보하는 사이) 다른 요청이 무효화하면 그 결과를 캐시에 쓰면 안 된다.

    get_runtime_settings가 select_all_settings를 기다리는 동안 다른 요청이 설정을
    저장하고 invalidate_runtime_settings()를 호출하는 상황을 재현한다. 이 몽키패치는
    원래 쿼리로 행을 다 받은 "직후"(마지막 __anext__ 호출, 즉 list comprehension이
    아직 실행 중인 시점)에 invalidate_runtime_settings()를 불러 그 인터리빙을 흉내낸다.
    반환값 자체는 정상이어야 하지만(파싱은 이미 끝났으므로), 그 결과가 stale write로
    _cache에 다시 쓰이면 안 된다 — 다음 호출도 다시 DB를 읽어야 한다.
    """
    original = queries.select_all_settings

    async def _racy_select(conn_arg):
        async for row in original(conn_arg):
            yield row
        invalidate_runtime_settings()

    monkeypatch.setattr(queries, "select_all_settings", _racy_select)

    conn = await raw_connection(db_session)
    rs = await get_runtime_settings(conn)
    assert rs.render_font_size == 30  # 파싱 결과 자체는 정상적으로 반환된다

    import app.runtime_settings as rts

    assert rts._cache is None  # 그러나 stale 스냅샷이 캐시에 남아있지 않아야 한다


async def test_db_failure_falls_back_to_defaults_without_raising(db_session, monkeypatch):
    """설정 테이블 장애가 파이프라인 전체를 멈추게 하지 않는다."""
    async def _boom(*args, **kwargs):
        # 실제 select_all_settings처럼 async generator여야 async for 소비 경로를
        # 그대로 탄다 — 행을 내주려는 순간(첫 __anext__) 예외가 난다.
        raise RuntimeError("relation does not exist")
        yield  # pragma: no cover - 이 줄 때문에 async generator 함수가 된다

    monkeypatch.setattr(queries, "select_all_settings", _boom)
    conn = await raw_connection(db_session)
    rs = await get_runtime_settings(conn)
    assert rs.render_font_size == 30

    import app.runtime_settings as rts

    assert rts._cache is None  # 장애 응답이 캐시에 쓰여 30초간 재시도를 막으면 안 된다
