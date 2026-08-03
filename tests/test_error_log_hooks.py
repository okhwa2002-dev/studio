from httpx import ASGITransport, AsyncClient

from app.db import raw_connection


async def _rows(db_session):
    conn = await raw_connection(db_session)
    return [dict(r) for r in await conn.fetch("SELECT * FROM error_logs ORDER BY id")]


async def test_unhandled_http_exception_is_recorded(db_session, error_sink):
    from app.main import app

    @app.get("/_hook_boom")
    async def _hook_boom():
        raise RuntimeError("핸들러가 터졌다")

    transport = ASGITransport(app=app, raise_app_exceptions=False)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/_hook_boom")

    # 응답은 기존과 동일하다 — 기록이 붙어도 사용자에게 보이는 것은 바뀌지 않는다.
    assert resp.status_code == 500
    assert resp.json() == {"code": "UNKNOWN_ERROR", "message": "알 수 없는 오류가 발생했습니다."}

    rows = await _rows(db_session)
    assert len(rows) == 1
    assert rows[0]["source"] == "http"
    assert rows[0]["exc_type"] == "RuntimeError"
    assert rows[0]["context"] == "GET /_hook_boom"


async def test_reset_mail_failure_is_recorded(db_session, error_sink, monkeypatch):
    """메일 발송 실패는 사용자에게도 관리자에게도 안 알린다 — 여기가 유일한 흔적이다."""
    from app.auth import password_reset

    async def _boom(to, subject, body):
        raise RuntimeError("SMTP 연결 실패")

    monkeypatch.setattr(password_reset, "send_email", _boom)

    await password_reset.deliver_reset_code("user@example.com", "042917")

    rows = await _rows(db_session)
    assert len(rows) == 1
    assert rows[0]["source"] == "email"
    assert rows[0]["context"] == "to=user@example.com"


async def test_reset_mail_failure_record_has_no_code(db_session, error_sink, monkeypatch):
    """인증코드는 어떤 컬럼에도 들어가면 안 된다(재설정 설계가 지켜 온 규칙)."""
    from app.auth import password_reset

    async def _boom(to, subject, body):
        raise RuntimeError("SMTP 연결 실패")

    monkeypatch.setattr(password_reset, "send_email", _boom)

    await password_reset.deliver_reset_code("user@example.com", "042917")

    rows = await _rows(db_session)
    assert "042917" not in " ".join(str(v) for v in rows[0].values())
