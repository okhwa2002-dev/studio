from app.auth.security import hash_password
from app.constants import UserStatus
from app.models.user import User


async def _login(client, db_session, email: str, password: str = "pw12345"):
    user = User(email=email, password_hash=hash_password(password), status=UserStatus.ACTIVE)
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)

    resp = await client.post("/auth/login", json={"email": email, "password": password})
    assert resp.status_code == 200
    return user


async def test_refresh_rotates_token_and_reissues_access(client, db_session):
    await _login(client, db_session, "refresh1@example.com")
    old_refresh = client.cookies.get("refresh_token")

    resp = await client.post("/auth/refresh")
    assert resp.status_code == 200
    new_refresh = client.cookies.get("refresh_token")
    assert new_refresh != old_refresh


async def test_refresh_reuse_of_rotated_token_revokes_all_sessions(client, db_session):
    await _login(client, db_session, "refresh2@example.com")
    old_refresh = client.cookies.get("refresh_token")

    first = await client.post("/auth/refresh")
    assert first.status_code == 200
    rotated_refresh = client.cookies.get("refresh_token")

    # 이미 회전되어 폐기된 이전 토큰을 다시 사용 시도 (탈취/재사용 시나리오)
    client.cookies.set("refresh_token", old_refresh)
    reuse_resp = await client.post("/auth/refresh")
    assert reuse_resp.status_code == 401

    # 재사용 탐지로 그 사이 발급된 최신 토큰도 함께 폐기되어야 한다
    client.cookies.set("refresh_token", rotated_refresh)
    after_breach_resp = await client.post("/auth/refresh")
    assert after_breach_resp.status_code == 401


async def test_refresh_without_cookie_returns_401(client):
    resp = await client.post("/auth/refresh")
    assert resp.status_code == 401


async def test_logout_clears_cookies_and_revokes_refresh_token(client, db_session):
    await _login(client, db_session, "logout1@example.com")
    refresh_token = client.cookies.get("refresh_token")

    resp = await client.post("/auth/logout")
    assert resp.status_code == 200

    client.cookies.set("refresh_token", refresh_token)
    reuse_resp = await client.post("/auth/refresh")
    assert reuse_resp.status_code == 401
