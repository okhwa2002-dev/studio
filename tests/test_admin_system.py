from app.auth.security import hash_password
from app.constants import UserRole, UserStatus
from app.db import raw_connection
from app.models.user import User


async def _login(client, db_session, email: str, role: str = UserRole.ADMIN) -> User:
    user = User(
        email=email,
        password_hash=hash_password("pw12345678"),
        role=role,
        status=UserStatus.ACTIVE,
        name="관리자",
    )
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)

    resp = await client.post(
        "/api/auth/login", json={"email": email, "password": "pw12345678"}
    )
    assert resp.status_code == 200
    return user


async def test_get_returns_defaults_when_nothing_overridden(client, db_session):
    await _login(client, db_session, "sys-get@example.com")

    resp = await client.get("/api/admin/system/settings")
    assert resp.status_code == 200
    body = resp.json()
    assert body["settings"]["render_font_size"] == 30
    assert body["settings"] == body["defaults"]
    assert body["overridden"] == []


async def test_put_saves_changed_value_and_marks_it_overridden(client, db_session):
    await _login(client, db_session, "sys-put@example.com")
    current = (await client.get("/api/admin/system/settings")).json()["settings"]

    resp = await client.put(
        "/api/admin/system/settings", json={**current, "render_font_size": 48}
    )
    assert resp.status_code == 200
    assert resp.json()["settings"]["render_font_size"] == 48
    assert resp.json()["overridden"] == ["render_font_size"]

    # 다시 읽어도 유지된다 (캐시 무효화가 걸렸다는 뜻이기도 하다)
    again = await client.get("/api/admin/system/settings")
    assert again.json()["settings"]["render_font_size"] == 48


async def test_put_back_to_default_removes_the_row(client, db_session):
    """기본값과 같아지면 행을 지운다 — 그래야 이후 .env 변경이 그대로 반영된다."""
    await _login(client, db_session, "sys-reset@example.com")
    current = (await client.get("/api/admin/system/settings")).json()["settings"]

    await client.put("/api/admin/system/settings", json={**current, "render_font_size": 48})
    resp = await client.put(
        "/api/admin/system/settings", json={**current, "render_font_size": 30}
    )

    assert resp.status_code == 200
    assert resp.json()["overridden"] == []

    from sqlalchemy import text

    row = await db_session.execute(text("SELECT COUNT(*) FROM system_settings"))
    assert row.scalar() == 0


async def test_put_back_to_default_removes_the_row_for_bool(client, db_session):
    """bool도 delete-on-default가 성립해야 한다.

    Python의 False == 0 / True == 1 동등성 때문에 이 비교가 가장 깨지기 쉬운 타입이
    bool이다. 깨지면 그 키는 행이 남은 채 .env 변경에 영원히 반응하지 않는다 —
    int(render_font_size) 하나로만 검증하던 공백을 메운다.
    """
    await _login(client, db_session, "sys-reset-bool@example.com")
    current = (await client.get("/api/admin/system/settings")).json()["settings"]
    assert current["signup_auto_approve"] is False  # conftest가 고정한 .env 기본값

    on = await client.put(
        "/api/admin/system/settings", json={**current, "signup_auto_approve": True}
    )
    assert on.status_code == 200
    assert on.json()["overridden"] == ["signup_auto_approve"]

    off = await client.put(
        "/api/admin/system/settings", json={**current, "signup_auto_approve": False}
    )
    assert off.status_code == 200
    assert off.json()["overridden"] == []

    from sqlalchemy import text

    row = await db_session.execute(text("SELECT COUNT(*) FROM system_settings"))
    assert row.scalar() == 0


async def test_put_rejects_out_of_range_value(client, db_session):
    await _login(client, db_session, "sys-range@example.com")
    current = (await client.get("/api/admin/system/settings")).json()["settings"]

    resp = await client.put(
        "/api/admin/system/settings", json={**current, "password_min_len": 4}
    )
    assert resp.status_code == 422
    # 화면이 읽는 것은 code·message뿐이다. FastAPI 기본 {"detail": [...]}를 그대로
    # 내보내면 14개 필드 중 무엇이 문제인지 알 수 없는 "알 수 없는 오류"만 뜬다.
    body = resp.json()
    assert body["code"] == "VALIDATION_ERROR"
    assert "password_min_len" in body["message"]
    assert "8" in body["message"]  # 허용 하한이 메시지에 드러난다


async def test_put_rejects_unknown_provider(client, db_session):
    await _login(client, db_session, "sys-provider@example.com")
    current = (await client.get("/api/admin/system/settings")).json()["settings"]

    resp = await client.put(
        "/api/admin/system/settings", json={**current, "script_provider": "nope"}
    )
    assert resp.status_code == 422
    body = resp.json()
    assert body["code"] == "VALIDATION_ERROR"
    # 커스텀 validator의 한국어 메시지가 pydantic의 "Value error, " 접두사 없이 그대로 온다.
    assert body["message"].startswith("script_provider: 알 수 없는 provider입니다")


async def test_put_records_who_changed_it(client, db_session):
    admin = await _login(client, db_session, "sys-actor@example.com")
    current = (await client.get("/api/admin/system/settings")).json()["settings"]
    await client.put("/api/admin/system/settings", json={**current, "render_font_size": 48})

    from sqlalchemy import text

    row = await db_session.execute(
        text("SELECT updated_by FROM system_settings WHERE key = 'render_font_size'")
    )
    assert row.scalar() == admin.id


async def test_member_cannot_read_settings(client, db_session):
    await _login(client, db_session, "sys-member@example.com", role=UserRole.MEMBER)
    resp = await client.get("/api/admin/system/settings")
    assert resp.status_code == 403


async def test_member_cannot_write_settings(client, db_session):
    await _login(client, db_session, "sys-member-w@example.com", role=UserRole.MEMBER)
    resp = await client.put("/api/admin/system/settings", json={})
    assert resp.status_code == 403


async def test_anonymous_is_unauthorized(client):
    resp = await client.get("/api/admin/system/settings")
    assert resp.status_code == 401


async def test_settings_update_records_only_changed_keys(client, db_session):
    await _login(client, db_session, "system-audit@example.com")

    current = (await client.get("/api/admin/system/settings")).json()["settings"]
    body = {**current, "password_min_len": 12}
    resp = await client.put("/api/admin/system/settings", json=body)
    assert resp.status_code == 200

    conn = await raw_connection(db_session)
    rows = await conn.fetch("SELECT * FROM audit_logs WHERE action = 'SYSTEM_SETTINGS_UPDATE'")
    assert len(rows) == 1
    assert rows[0]["target_type"] == "SYSTEM"
    assert rows[0]["target_id"] is None
    assert rows[0]["summary"] == "password_min_len 8 → 12"


async def test_settings_update_without_changes_is_not_recorded(client, db_session):
    """화면이 폼 전체를 PUT하므로, 아무것도 안 바꾼 저장이 기록을 만들면 안 된다."""
    await _login(client, db_session, "system-audit2@example.com")

    current = (await client.get("/api/admin/system/settings")).json()["settings"]
    resp = await client.put("/api/admin/system/settings", json=current)
    assert resp.status_code == 200

    conn = await raw_connection(db_session)
    count = await conn.fetchval(
        "SELECT COUNT(*) FROM audit_logs WHERE action = 'SYSTEM_SETTINGS_UPDATE'"
    )
    assert count == 0
