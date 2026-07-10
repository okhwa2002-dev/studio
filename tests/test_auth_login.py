from app.auth.security import hash_password
from app.models.user import User


async def _create_user(db_session, email: str, password: str, status: str = "active") -> User:
    user = User(email=email, password_hash=hash_password(password), status=status)
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    return user


async def test_login_succeeds_for_active_user(client, db_session):
    await _create_user(db_session, "active@example.com", "pw12345")

    resp = await client.post(
        "/auth/login", json={"email": "active@example.com", "password": "pw12345"}
    )
    assert resp.status_code == 200
    assert resp.json()["email"] == "active@example.com"
    assert "access_token" in resp.cookies
    assert "refresh_token" in resp.cookies


async def test_login_rejects_wrong_password(client, db_session):
    await _create_user(db_session, "active2@example.com", "pw12345")

    resp = await client.post(
        "/auth/login", json={"email": "active2@example.com", "password": "wrong-pw"}
    )
    assert resp.status_code == 401


async def test_login_rejects_unknown_email(client):
    resp = await client.post(
        "/auth/login", json={"email": "nobody@example.com", "password": "pw12345"}
    )
    assert resp.status_code == 401


async def test_login_rejects_pending_user(client, db_session):
    await _create_user(db_session, "pending@example.com", "pw12345", status="pending")

    resp = await client.post(
        "/auth/login", json={"email": "pending@example.com", "password": "pw12345"}
    )
    assert resp.status_code == 403
