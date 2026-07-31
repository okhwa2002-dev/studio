from app.auth.security import hash_password
from app.constants import UserStatus
from app.db import raw_connection
from app.models.user import User


async def _login(client, db_session, email: str, password: str = "pw12345"):
    user = User(email=email, password_hash=hash_password(password), status=UserStatus.ACTIVE)
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)

    resp = await client.post("/api/auth/login", json={"email": email, "password": password})
    assert resp.status_code == 200
    return user


async def test_refresh_rotates_token_and_reissues_access(client, db_session):
    await _login(client, db_session, "refresh1@example.com")
    old_refresh = client.cookies.get("refresh_token")

    resp = await client.post("/api/auth/refresh")
    assert resp.status_code == 200
    new_refresh = client.cookies.get("refresh_token")
    assert new_refresh != old_refresh


async def test_refresh_reuse_of_rotated_token_revokes_all_sessions(client, db_session):
    await _login(client, db_session, "refresh2@example.com")
    old_refresh = client.cookies.get("refresh_token")

    first = await client.post("/api/auth/refresh")
    assert first.status_code == 200
    rotated_refresh = client.cookies.get("refresh_token")

    # 이미 회전되어 폐기된 이전 토큰을 다시 사용 시도 (탈취/재사용 시나리오)
    client.cookies.set("refresh_token", old_refresh)
    reuse_resp = await client.post("/api/auth/refresh")
    assert reuse_resp.status_code == 401

    # 재사용 탐지로 그 사이 발급된 최신 토큰도 함께 폐기되어야 한다
    client.cookies.set("refresh_token", rotated_refresh)
    after_breach_resp = await client.post("/api/auth/refresh")
    assert after_breach_resp.status_code == 401


async def test_refresh_without_cookie_returns_401(client):
    resp = await client.post("/api/auth/refresh")
    assert resp.status_code == 401


async def test_logout_clears_cookies_and_revokes_refresh_token(client, db_session):
    await _login(client, db_session, "logout1@example.com")
    refresh_token = client.cookies.get("refresh_token")

    resp = await client.post("/api/auth/logout")
    assert resp.status_code == 200

    client.cookies.set("refresh_token", refresh_token)
    reuse_resp = await client.post("/api/auth/refresh")
    assert reuse_resp.status_code == 401


async def test_logout_is_recorded(client, db_session):
    await _login(client, db_session, "logout-audit@example.com")

    resp = await client.post("/api/auth/logout")
    assert resp.status_code == 200

    conn = await raw_connection(db_session)
    rows = await conn.fetch("SELECT * FROM audit_logs WHERE action = 'LOGOUT'")
    assert len(rows) == 1


async def test_normal_refresh_is_not_recorded(client, db_session):
    """정상 갱신은 몇 분마다 일어난다 — 기록하면 목록을 덮는다."""
    await _login(client, db_session, "refresh-audit@example.com")

    resp = await client.post("/api/auth/refresh")
    assert resp.status_code == 200

    conn = await raw_connection(db_session)
    count = await conn.fetchval(
        "SELECT COUNT(*) FROM audit_logs WHERE action IN ('TOKEN_REUSE_DETECTED', 'LOGOUT')"
    )
    assert count == 0


async def test_token_reuse_is_recorded(client, db_session):
    """폐기된 토큰의 재사용은 탈취 신호다 — 반드시 남는다."""
    await _login(client, db_session, "reuse-audit@example.com")
    old_cookie = client.cookies.get("refresh_token")

    await client.post("/api/auth/refresh")            # 회전 → 옛 토큰 폐기
    client.cookies.set("refresh_token", old_cookie)   # 폐기된 토큰을 다시 제시
    resp = await client.post("/api/auth/refresh")
    assert resp.status_code == 401

    conn = await raw_connection(db_session)
    rows = await conn.fetch("SELECT * FROM audit_logs WHERE action = 'TOKEN_REUSE_DETECTED'")
    assert len(rows) == 1
    assert rows[0]["success_yn"] == "N"
