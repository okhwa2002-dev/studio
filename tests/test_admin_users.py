from app.auth.security import hash_password
from app.constants import UserRole, UserStatus
from app.models.user import User


async def _login_admin(client, db_session, email: str = "admin1@example.com") -> User:
    admin = User(
        email=email, password_hash=hash_password("pw12345"), role=UserRole.ADMIN, status=UserStatus.ACTIVE
    )
    db_session.add(admin)
    await db_session.commit()
    await db_session.refresh(admin)

    resp = await client.post("/api/auth/login", json={"email": email, "password": "pw12345"})
    assert resp.status_code == 200
    return admin


async def test_list_pending_users(client, db_session):
    await _login_admin(client, db_session)
    pending = User(email="pending-list@example.com", password_hash=hash_password("pw12345"))
    db_session.add(pending)
    await db_session.commit()

    resp = await client.get("/api/admin/users", params={"status": UserStatus.PENDING})
    assert resp.status_code == 200
    emails = [row["email"] for row in resp.json()]
    assert "pending-list@example.com" in emails


async def test_approve_user_sets_status_active(client, db_session):
    admin = await _login_admin(client, db_session, email="admin2@example.com")
    target = User(email="to-approve@example.com", password_hash=hash_password("pw12345"))
    db_session.add(target)
    await db_session.commit()
    await db_session.refresh(target)

    resp = await client.post(f"/api/admin/users/{target.id}/approve")
    assert resp.status_code == 200
    assert resp.json()["status"] == UserStatus.ACTIVE


async def test_reject_user_sets_status_rejected(client, db_session):
    await _login_admin(client, db_session, email="admin3@example.com")
    target = User(email="to-reject@example.com", password_hash=hash_password("pw12345"))
    db_session.add(target)
    await db_session.commit()
    await db_session.refresh(target)

    resp = await client.post(f"/api/admin/users/{target.id}/reject")
    assert resp.status_code == 200
    assert resp.json()["status"] == UserStatus.REJECTED


async def test_approve_unknown_user_returns_404(client, db_session):
    await _login_admin(client, db_session, email="admin4@example.com")

    resp = await client.post("/api/admin/users/999999/approve")
    assert resp.status_code == 404


async def test_admin_endpoints_reject_non_admin(client, db_session):
    member = User(
        email="member-blocked@example.com", password_hash=hash_password("pw12345"),
        role=UserRole.MEMBER, status=UserStatus.ACTIVE,
    )
    db_session.add(member)
    await db_session.commit()

    resp = await client.post(
        "/api/auth/login", json={"email": "member-blocked@example.com", "password": "pw12345"}
    )
    assert resp.status_code == 200

    resp = await client.get("/api/admin/users", params={"status": UserStatus.PENDING})
    assert resp.status_code == 403


async def test_list_users_rejects_unknown_status(client, db_session):
    await _login_admin(client, db_session, email="admin5@example.com")

    resp = await client.get("/api/admin/users", params={"status": "nonsense"})
    assert resp.status_code == 422
