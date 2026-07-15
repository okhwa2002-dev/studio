import app.auth.router as auth_router
from app.auth.security import hash_password
from app.constants import UserStatus
from app.db import raw_connection
from app.models.user import User
from app.queries import queries


async def test_new_user_lock_fields_default(db_session):
    user = User(email="lockdefault@example.com", password_hash=hash_password("pw12345"))
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    assert user.failed_login_count == 0
    assert user.locked_at is None
    assert user.unlocked_at is None


async def test_find_by_email_returns_lock_fields(db_session):
    # 로그인 로직이 읽을 수 있도록 SELECT가 잠금 컬럼을 포함해야 한다.
    user = User(email="lockcols@example.com", password_hash=hash_password("pw12345"), status=UserStatus.ACTIVE)
    db_session.add(user)
    await db_session.commit()
    conn = await raw_connection(db_session)
    row = await queries.find_by_email(conn, email="lockcols@example.com")
    assert "failed_login_count" in row
    assert "locked_at" in row
    assert "unlocked_at" in row


async def _active(db_session, email, password="pw12345"):
    user = User(email=email, password_hash=hash_password(password), status=UserStatus.ACTIVE)
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    return user


async def test_five_failures_locks_account(client, db_session):
    user = await _active(db_session, "lock5@example.com")
    for _ in range(5):
        resp = await client.post("/auth/login", json={"email": "lock5@example.com", "password": "wrong"})
        assert resp.status_code == 401  # 매 응답은 통일 401
    await db_session.refresh(user)
    assert user.failed_login_count == 5
    assert user.locked_at is not None


async def test_locked_account_correct_password_returns_423(client, db_session):
    user = await _active(db_session, "locked423@example.com")
    for _ in range(5):
        await client.post("/auth/login", json={"email": "locked423@example.com", "password": "wrong"})
    resp = await client.post("/auth/login", json={"email": "locked423@example.com", "password": "pw12345"})
    assert resp.status_code == 423
    assert "access_token" not in resp.cookies


async def test_locked_account_wrong_password_still_401(client, db_session):
    # 잠긴 계정이라도 오답에는 통일 401 — 공격자에게 잠김이 드러나지 않는다.
    await _active(db_session, "lockedwrong@example.com")
    for _ in range(5):
        await client.post("/auth/login", json={"email": "lockedwrong@example.com", "password": "wrong"})
    resp = await client.post("/auth/login", json={"email": "lockedwrong@example.com", "password": "wrong"})
    assert resp.status_code == 401


async def test_successful_login_resets_failure_count(client, db_session):
    user = await _active(db_session, "reset@example.com")
    for _ in range(3):
        await client.post("/auth/login", json={"email": "reset@example.com", "password": "wrong"})
    resp = await client.post("/auth/login", json={"email": "reset@example.com", "password": "pw12345"})
    assert resp.status_code == 200
    await db_session.refresh(user)
    assert user.failed_login_count == 0


async def test_lock_threshold_is_configurable(client, db_session, monkeypatch):
    user = await _active(db_session, "cfg@example.com")
    # 캐시된 settings 인스턴스의 속성만 바꾼다(monkeypatch가 자동 복원).
    monkeypatch.setattr(auth_router.get_settings(), "failed_login_limit", 3)
    for _ in range(3):
        await client.post("/auth/login", json={"email": "cfg@example.com", "password": "wrong"})
    await db_session.refresh(user)
    assert user.locked_at is not None
