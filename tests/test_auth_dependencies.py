from fastapi import Depends

from app.auth.dependencies import current_user, require_admin
from app.auth.security import hash_password
from app.main import app
from app.models.user import User


async def _login(client, db_session, email: str, role: str = "member", password: str = "pw12345"):
    user = User(email=email, password_hash=hash_password(password), role=role, status="active")
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)

    resp = await client.post("/auth/login", json={"email": email, "password": password})
    assert resp.status_code == 200
    return user


async def test_current_user_rejects_missing_cookie(client):
    @app.get("/_whoami")
    async def _whoami(user: dict = Depends(current_user)):
        return {"email": user["email"]}

    resp = await client.get("/_whoami")
    assert resp.status_code == 401


async def test_current_user_returns_user_after_login(client, db_session):
    @app.get("/_whoami2")
    async def _whoami2(user: dict = Depends(current_user)):
        return {"email": user["email"]}

    await _login(client, db_session, "whoami@example.com")

    resp = await client.get("/_whoami2")
    assert resp.status_code == 200
    assert resp.json()["email"] == "whoami@example.com"


async def test_require_admin_rejects_non_admin(client, db_session):
    @app.get("/_admin_only")
    async def _admin_only(user: dict = Depends(require_admin)):
        return {"email": user["email"]}

    await _login(client, db_session, "member-only@example.com", role="member")

    resp = await client.get("/_admin_only")
    assert resp.status_code == 403


async def test_current_user_excludes_password_hash(client, db_session):
    @app.get("/_whoami3")
    async def _whoami3(user: dict = Depends(current_user)):
        return {"keys": sorted(user.keys())}

    await _login(client, db_session, "no-hash-leak@example.com")

    resp = await client.get("/_whoami3")
    assert resp.status_code == 200
    assert "password_hash" not in resp.json()["keys"]


async def test_require_admin_allows_admin(client, db_session):
    @app.get("/_admin_only2")
    async def _admin_only2(user: dict = Depends(require_admin)):
        return {"email": user["email"]}

    await _login(client, db_session, "admin-user@example.com", role="admin")

    resp = await client.get("/_admin_only2")
    assert resp.status_code == 200
    assert resp.json()["email"] == "admin-user@example.com"
