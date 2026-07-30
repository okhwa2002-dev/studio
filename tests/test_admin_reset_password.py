"""관리자 비밀번호 초기화 — POST /api/admin/users/{id}/reset-password"""

from app.auth.security import INITIAL_PASSWORD, hash_password
from app.constants import UserRole, UserStatus
from app.models.user import User
from app.queries import queries
from app.utils.time import now_local


async def _login_admin(client, db_session, email: str) -> User:
    admin = User(
        email=email,
        password_hash=hash_password("pw12345"),
        role=UserRole.ADMIN,
        status=UserStatus.ACTIVE,
    )
    db_session.add(admin)
    await db_session.commit()
    await db_session.refresh(admin)

    resp = await client.post("/api/auth/login", json={"email": email, "password": "pw12345"})
    assert resp.status_code == 200
    return admin


async def _add_member(db_session, email: str, **kwargs) -> User:
    member = User(
        email=email,
        password_hash=hash_password("original-pw"),
        role=UserRole.MEMBER,
        status=UserStatus.ACTIVE,
        **kwargs,
    )
    db_session.add(member)
    await db_session.commit()
    await db_session.refresh(member)
    return member


async def test_reset_password_returns_temp_password_that_can_log_in(client, db_session):
    """초기화 응답의 temp_password로 실제 로그인이 된다."""
    await _login_admin(client, db_session, "admin-rp1@example.com")
    target = await _add_member(db_session, "rp-login@example.com")

    resp = await client.post(f"/api/admin/users/{target.id}/reset-password")
    assert resp.status_code == 200
    temp = resp.json()["temp_password"]
    assert temp == INITIAL_PASSWORD

    # 관리자 세션 쿠키를 버리고, 대상 사용자로 임시 비밀번호 로그인을 시도한다.
    client.cookies.clear()
    login = await client.post(
        "/api/auth/login", json={"email": "rp-login@example.com", "password": temp}
    )
    assert login.status_code == 200


async def test_reset_password_invalidates_the_old_password(client, db_session):
    await _login_admin(client, db_session, "admin-rp2@example.com")
    target = await _add_member(db_session, "rp-old@example.com")

    assert (await client.post(f"/api/admin/users/{target.id}/reset-password")).status_code == 200

    client.cookies.clear()
    login = await client.post(
        "/api/auth/login", json={"email": "rp-old@example.com", "password": "original-pw"}
    )
    assert login.status_code == 401


async def test_reset_password_sets_must_change_password(client, db_session):
    await _login_admin(client, db_session, "admin-rp3@example.com")
    target = await _add_member(db_session, "rp-flag@example.com")

    assert (await client.post(f"/api/admin/users/{target.id}/reset-password")).status_code == 200

    listed = await client.get("/api/admin/users")
    row = next(u for u in listed.json() if u["email"] == "rp-flag@example.com")
    assert row["must_change_password"] is True


async def test_reset_password_unlocks_and_clears_failures(client, db_session):
    """비밀번호를 잊어 연속 실패로 잠긴 계정이 가장 흔한 초기화 대상이다 — 함께 풀린다."""
    await _login_admin(client, db_session, "admin-rp4@example.com")
    target = await _add_member(
        db_session, "rp-locked@example.com", failed_login_count=5, locked_at=now_local()
    )

    resp = await client.post(f"/api/admin/users/{target.id}/reset-password")
    assert resp.status_code == 200
    assert resp.json()["unlocked_at"] is not None

    listed = await client.get("/api/admin/users")
    row = next(u for u in listed.json() if u["email"] == "rp-locked@example.com")
    assert row["locked_at"] is None
    assert row["failed_login_count"] == 0
    assert row["unlocked_at"] is not None


async def test_reset_password_revokes_target_refresh_tokens(client, db_session):
    """초기화 전에 발급된 세션은 끊긴다 — 탈취 대응이 초기화의 동기일 수 있다."""
    admin = await _login_admin(client, db_session, "admin-rp5@example.com")
    target = await _add_member(db_session, "rp-session@example.com")

    # 대상 사용자로 로그인해 refresh 쿠키를 얻는다.
    client.cookies.clear()
    login = await client.post(
        "/api/auth/login", json={"email": "rp-session@example.com", "password": "original-pw"}
    )
    assert login.status_code == 200
    victim_refresh = client.cookies["refresh_token"]

    # 관리자로 되돌아와 초기화한다.
    client.cookies.clear()
    await client.post("/api/auth/login", json={"email": admin.email, "password": "pw12345"})
    assert (await client.post(f"/api/admin/users/{target.id}/reset-password")).status_code == 200

    # 초기화 전에 받아둔 refresh 토큰은 더 이상 통하지 않는다.
    client.cookies.clear()
    client.cookies.set("refresh_token", victim_refresh)
    assert (await client.post("/api/auth/refresh")).status_code == 401


async def test_reset_password_keeps_other_users_sessions(client, db_session):
    """폐기 범위는 대상 사용자 한 명이다."""
    admin = await _login_admin(client, db_session, "admin-rp6@example.com")
    target = await _add_member(db_session, "rp-target@example.com")
    bystander = await _add_member(db_session, "rp-bystander@example.com")

    client.cookies.clear()
    await client.post(
        "/api/auth/login", json={"email": bystander.email, "password": "original-pw"}
    )
    bystander_refresh = client.cookies["refresh_token"]

    client.cookies.clear()
    await client.post("/api/auth/login", json={"email": admin.email, "password": "pw12345"})
    assert (await client.post(f"/api/admin/users/{target.id}/reset-password")).status_code == 200

    client.cookies.clear()
    client.cookies.set("refresh_token", bystander_refresh)
    assert (await client.post("/api/auth/refresh")).status_code == 200


async def test_reset_password_records_admin_as_updated_by(client, db_session):
    admin = await _login_admin(client, db_session, "admin-rp7@example.com")
    target = await _add_member(db_session, "rp-audit@example.com")

    assert (await client.post(f"/api/admin/users/{target.id}/reset-password")).status_code == 200

    from app.db import raw_connection

    conn = await raw_connection(db_session)
    row = await queries.find_by_id(conn, id=target.id)
    assert row["updated_by"] == admin.id


async def test_reset_password_rejects_self(client, db_session):
    """본인 초기화는 막는다 — 스스로 로그아웃된 뒤 강제 변경 화면에 갇힌다."""
    admin = await _login_admin(client, db_session, "admin-rp8@example.com")

    resp = await client.post(f"/api/admin/users/{admin.id}/reset-password")
    assert resp.status_code == 400

    # 자기 비밀번호는 그대로여야 한다.
    client.cookies.clear()
    login = await client.post(
        "/api/auth/login", json={"email": admin.email, "password": "pw12345"}
    )
    assert login.status_code == 200


async def test_reset_password_allows_other_admin(client, db_session):
    """다른 관리자는 초기화할 수 있다 — 관리자가 비밀번호를 잃었을 때의 유일한 경로다."""
    await _login_admin(client, db_session, "admin-rp9@example.com")
    other = await _login_admin(client, db_session, "admin-rp9-other@example.com")

    # _login_admin이 other로 로그인해 두었으므로 첫 관리자로 되돌아온다.
    client.cookies.clear()
    await client.post(
        "/api/auth/login", json={"email": "admin-rp9@example.com", "password": "pw12345"}
    )

    resp = await client.post(f"/api/admin/users/{other.id}/reset-password")
    assert resp.status_code == 200


async def test_reset_password_unknown_user_returns_404(client, db_session):
    await _login_admin(client, db_session, "admin-rp10@example.com")

    resp = await client.post("/api/admin/users/999999/reset-password")
    assert resp.status_code == 404


async def test_reset_password_rejects_non_admin(client, db_session):
    member = await _add_member(db_session, "rp-member@example.com")
    victim = await _add_member(db_session, "rp-victim@example.com")

    login = await client.post(
        "/api/auth/login", json={"email": member.email, "password": "original-pw"}
    )
    assert login.status_code == 200

    resp = await client.post(f"/api/admin/users/{victim.id}/reset-password")
    assert resp.status_code == 403
