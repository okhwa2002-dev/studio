import app.auth.router as auth_router
from app.auth.security import hash_password
from app.constants import UserRole, UserStatus
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
        resp = await client.post("/api/auth/login", json={"email": "lock5@example.com", "password": "wrong"})
        assert resp.status_code == 401  # 매 응답은 통일 401
    await db_session.refresh(user)
    assert user.failed_login_count == 5
    assert user.locked_at is not None


async def test_locked_account_correct_password_returns_423(client, db_session):
    user = await _active(db_session, "locked423@example.com")
    for _ in range(5):
        await client.post("/api/auth/login", json={"email": "locked423@example.com", "password": "wrong"})
    resp = await client.post("/api/auth/login", json={"email": "locked423@example.com", "password": "pw12345"})
    assert resp.status_code == 423
    assert "access_token" not in resp.cookies


async def test_locked_account_correct_password_login_failure_is_committed(client, db_session):
    """423로 끝나는 경로도 커밋에 도달하지 않는다 — record_failure가 없으면 기록이 사라진다.

    잠금을 만드는 준비는 test_locked_account_correct_password_returns_423과 같은 방식
    (5회 오답으로 잠금)을 쓴다. 롤백 후에도 남아 있는지가 실제로 커밋됐는지를
    가르는 유일한 신호다(conftest의 SAVEPOINT 격리 때문에 별도 세션으로는 확인 불가).
    """
    await _active(db_session, "locked423-audit@example.com")
    for _ in range(5):
        await client.post(
            "/api/auth/login", json={"email": "locked423-audit@example.com", "password": "wrong"}
        )

    resp = await client.post(
        "/api/auth/login", json={"email": "locked423-audit@example.com", "password": "pw12345"}
    )
    assert resp.status_code == 423

    await db_session.rollback()

    conn = await raw_connection(db_session)
    rows = await conn.fetch(
        "SELECT * FROM audit_logs WHERE action = 'LOGIN_FAILURE' AND summary = '잠긴 계정'"
    )
    assert len(rows) == 1


async def test_locked_account_wrong_password_still_401(client, db_session):
    # 잠긴 계정이라도 오답에는 통일 401 — 공격자에게 잠김이 드러나지 않는다.
    await _active(db_session, "lockedwrong@example.com")
    for _ in range(5):
        await client.post("/api/auth/login", json={"email": "lockedwrong@example.com", "password": "wrong"})
    resp = await client.post("/api/auth/login", json={"email": "lockedwrong@example.com", "password": "wrong"})
    assert resp.status_code == 401


async def test_successful_login_resets_failure_count(client, db_session):
    user = await _active(db_session, "reset@example.com")
    for _ in range(3):
        await client.post("/api/auth/login", json={"email": "reset@example.com", "password": "wrong"})
    resp = await client.post("/api/auth/login", json={"email": "reset@example.com", "password": "pw12345"})
    assert resp.status_code == 200
    await db_session.refresh(user)
    assert user.failed_login_count == 0


async def test_lock_threshold_is_configurable(client, db_session, monkeypatch):
    user = await _active(db_session, "cfg@example.com")
    # 캐시된 settings 인스턴스의 속성만 바꾼다(monkeypatch가 자동 복원).
    monkeypatch.setattr(auth_router.get_settings(), "failed_login_limit", 3)
    for _ in range(3):
        await client.post("/api/auth/login", json={"email": "cfg@example.com", "password": "wrong"})
    await db_session.refresh(user)
    assert user.locked_at is not None


async def _login_admin(client, db_session, email="lockadmin@example.com"):
    admin = User(email=email, password_hash=hash_password("pw12345"), role=UserRole.ADMIN, status=UserStatus.ACTIVE)
    db_session.add(admin)
    await db_session.commit()
    await db_session.refresh(admin)
    resp = await client.post("/api/auth/login", json={"email": email, "password": "pw12345"})
    assert resp.status_code == 200
    return admin


async def test_unlock_clears_lock_and_resets_count(client, db_session):
    await _login_admin(client, db_session, email="unlockadmin@example.com")
    target = await _active(db_session, "tounlock@example.com")
    for _ in range(5):
        await client.post("/api/auth/login", json={"email": "tounlock@example.com", "password": "wrong"})
    await db_session.refresh(target)
    assert target.locked_at is not None

    resp = await client.post(f"/api/admin/users/{target.id}/unlock")
    assert resp.status_code == 200
    await db_session.refresh(target)
    assert target.locked_at is None
    assert target.failed_login_count == 0
    assert target.unlocked_at is not None

    # 해제 후 다시 로그인 가능
    resp = await client.post("/api/auth/login", json={"email": "tounlock@example.com", "password": "pw12345"})
    assert resp.status_code == 200


async def test_unlock_unknown_user_returns_404(client, db_session):
    await _login_admin(client, db_session, email="unlock404@example.com")
    resp = await client.post("/api/admin/users/999999/unlock")
    assert resp.status_code == 404


async def test_unlock_rejects_non_admin(client, db_session):
    member = User(email="unlockmember@example.com", password_hash=hash_password("pw12345"), role=UserRole.MEMBER, status=UserStatus.ACTIVE)
    db_session.add(member)
    await db_session.commit()
    await client.post("/api/auth/login", json={"email": "unlockmember@example.com", "password": "pw12345"})
    resp = await client.post("/api/admin/users/1/unlock")
    assert resp.status_code == 403


async def test_lock_is_recorded_once_at_the_threshold(client, db_session):
    """잠기는 순간에만 ACCOUNT_LOCKED가 남고, 그 뒤 시도는 LOGIN_FAILURE만 쌓인다."""
    await _active(db_session, "lock-audit@example.com")
    conn = await raw_connection(db_session)

    # 기본 임계치는 conftest가 FAILED_LOGIN_LIMIT=5로 고정한다.
    for _ in range(6):
        await client.post(
            "/api/auth/login", json={"email": "lock-audit@example.com", "password": "wrong"}
        )

    locked = await conn.fetch("SELECT * FROM audit_logs WHERE action = 'ACCOUNT_LOCKED'")
    failures = await conn.fetch("SELECT * FROM audit_logs WHERE action = 'LOGIN_FAILURE'")
    assert len(locked) == 1
    assert locked[0]["summary"] == "연속 로그인 실패 5회로 잠김"
    assert locked[0]["target_type"] == "USER"
    assert len(failures) == 6
