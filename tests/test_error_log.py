import asyncio
import time
from contextlib import asynccontextmanager

from app.core import error_log
from app.core.error_log import SOURCE_HTTP, record_error
from app.db import raw_connection


def _boom(message="터짐") -> ValueError:
    """트레이스백이 붙은 예외를 만든다 — record_error가 거기서 위치를 뽑는다."""
    try:
        raise ValueError(message)
    except ValueError as exc:
        return exc


async def _rows(db_session):
    conn = await raw_connection(db_session)
    return [dict(r) for r in await conn.fetch("SELECT * FROM error_logs ORDER BY id")]


async def test_first_occurrence_creates_a_row(db_session, error_sink):
    await record_error(SOURCE_HTTP, _boom(), context="GET /api/health")

    rows = await _rows(db_session)
    assert len(rows) == 1
    assert rows[0]["count"] == 1
    assert rows[0]["source"] == "http"
    assert rows[0]["exc_type"] == "ValueError"
    assert rows[0]["message"] == "터짐"
    assert rows[0]["context"] == "GET /api/health"


async def test_location_points_at_the_raising_line(db_session, error_sink):
    """'디렉토리/파일:줄' 형식이어야 고칠 지점을 가리킨다.

    이 테스트 파일은 app 패키지 밖이라 앱 프레임이 없다 — 폴백(마지막 프레임)까지
    함께 고정된다.
    """
    await record_error(SOURCE_HTTP, _boom())

    location = (await _rows(db_session))[0]["location"]
    assert location.startswith("tests/test_error_log.py:")
    assert location.rsplit(":", 1)[1].isdigit()


async def test_same_fingerprint_is_merged(db_session, error_sink):
    for _ in range(3):
        await record_error(SOURCE_HTTP, _boom())

    rows = await _rows(db_session)
    assert len(rows) == 1
    assert rows[0]["count"] == 3


async def test_message_is_not_part_of_the_fingerprint(db_session, error_sink):
    """메시지를 지문에 넣으면 같은 버그가 지문 수천 개로 흩어진다."""
    await record_error(SOURCE_HTTP, _boom("사용자 12 처리 실패"))
    await record_error(SOURCE_HTTP, _boom("사용자 99 처리 실패"))

    rows = await _rows(db_session)
    assert len(rows) == 1
    assert rows[0]["count"] == 2
    # 마지막 발생 값으로 덮어쓴다.
    assert rows[0]["message"] == "사용자 99 처리 실패"


async def test_different_source_is_a_different_row(db_session, error_sink):
    await record_error(SOURCE_HTTP, _boom())
    await record_error("worker", _boom())

    assert len(await _rows(db_session)) == 2


async def test_message_is_clipped_to_200_chars(db_session, error_sink):
    await record_error(SOURCE_HTTP, _boom("가" * 500))

    rows = await _rows(db_session)
    assert len(rows[0]["message"]) == 200


async def test_no_traceback_is_stored(db_session, error_sink):
    """트레이스백 전문에는 값이 섞일 수 있다 — 어느 컬럼에도 들어가면 안 된다."""
    await record_error(SOURCE_HTTP, _boom(), context="GET /api/health")

    rows = await _rows(db_session)
    joined = " ".join(str(v) for v in rows[0].values())
    assert "Traceback" not in joined
    assert "\n" not in joined


async def test_failure_is_swallowed():
    """기록이 실패해도 호출자에게 전파되지 않는다 — 원래 응답을 더 망가뜨리면 안 된다."""

    @asynccontextmanager
    async def _broken():
        raise RuntimeError("DB 없음")
        yield  # pragma: no cover

    error_log.set_session_factory(_broken)

    await record_error(SOURCE_HTTP, _boom())  # 예외가 나지 않아야 한다


async def test_hanging_db_does_not_block_longer_than_the_timeout():
    """DB가 죽으면 모든 요청이 500이 나는데, 그때 기록이 매달리면 장애를 키운다."""

    @asynccontextmanager
    async def _hangs():
        await asyncio.sleep(30)
        yield  # pragma: no cover

    error_log.set_session_factory(_hangs)

    started = time.monotonic()
    await record_error(SOURCE_HTTP, _boom())
    elapsed = time.monotonic() - started

    assert elapsed < error_log.RECORD_TIMEOUT_SEC + 1


async def test_context_may_be_omitted(db_session, error_sink):
    """정리 잡 전체 실패처럼 넘길 부가 정보가 없는 호출부가 있다."""
    await record_error("cleanup", _boom())

    rows = await _rows(db_session)
    assert rows[0]["context"] is None
