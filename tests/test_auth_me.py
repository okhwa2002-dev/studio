from app.auth.security import hash_password
from app.constants import UserRole, UserStatus
from app.models.user import User


async def _login(client, db_session, email: str, role: str = UserRole.MEMBER, password: str = "pw12345"):
    user = User(email=email, password_hash=hash_password(password), role=role, status=UserStatus.ACTIVE)
    db_session.add(user)
    await db_session.commit()

    resp = await client.post("/auth/login", json={"email": email, "password": password})
    assert resp.status_code == 200


async def test_me_requires_authentication(client):
    resp = await client.get("/auth/me")
    assert resp.status_code == 401


async def test_me_rejects_invalid_token(client):
    client.cookies.set("access_token", "not-a-jwt")
    resp = await client.get("/auth/me")
    assert resp.status_code == 401


async def test_me_returns_current_user(client, db_session):
    await _login(client, db_session, "me@example.com")

    resp = await client.get("/auth/me")
    assert resp.status_code == 200
    body = resp.json()
    assert body["email"] == "me@example.com"
    assert body["role"] == UserRole.MEMBER
    assert isinstance(body["id"], int)


async def test_me_returns_admin_role(client, db_session):
    await _login(client, db_session, "me-admin@example.com", role=UserRole.ADMIN)

    resp = await client.get("/auth/me")
    assert resp.status_code == 200
    assert resp.json()["role"] == UserRole.ADMIN


async def test_me_does_not_leak_password_hash(client, db_session):
    await _login(client, db_session, "me-no-hash@example.com")

    resp = await client.get("/auth/me")
    assert resp.status_code == 200
    assert set(resp.json().keys()) == {"id", "email", "role"}
