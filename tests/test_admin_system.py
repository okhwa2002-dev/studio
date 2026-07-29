from app.auth.security import hash_password
from app.constants import UserRole, UserStatus
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
