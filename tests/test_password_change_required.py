"""강제 변경 게이트 — must_change_password인 사용자는 비밀번호를 바꿔야 계속할 수 있다."""

from app.auth.security import hash_password
from app.constants import UserRole, UserStatus
from app.models.user import User
from app.queries import queries


async def _login_must_change(client, db_session, email: str, role: str = UserRole.MEMBER) -> User:
    """must_change_password가 켜진 사용자를 만들고 로그인시킨다."""
    user = User(
        email=email,
        password_hash=hash_password("temp-pw1"),
        role=role,
        status=UserStatus.ACTIVE,
        must_change_password=True,
    )
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)

    resp = await client.post("/api/auth/login", json={"email": email, "password": "temp-pw1"})
    assert resp.status_code == 200, "강제 변경 상태여도 로그인은 성공해야 한다(막으면 바꿀 방법이 없다)"
    return user


async def test_login_succeeds_and_reports_the_flag(client, db_session):
    """로그인은 막지 않는다 — 응답의 플래그로 프론트가 강제 변경 화면을 띄운다."""
    await _login_must_change(client, db_session, "gate-login@example.com")

    # 프론트의 login은 /auth/me를 다시 부르지 않고 이 응답을 그대로 쓴다.
    resp = await client.post(
        "/api/auth/login", json={"email": "gate-login@example.com", "password": "temp-pw1"}
    )
    assert resp.json()["must_change_password"] is True


async def test_other_apis_are_blocked_with_403(client, db_session):
    await _login_must_change(client, db_session, "gate-blocked@example.com")

    resp = await client.get("/api/projects")
    assert resp.status_code == 403
    assert resp.json()["code"] == "PASSWORD_CHANGE_REQUIRED"


async def test_admin_apis_are_blocked_too(client, db_session):
    """게이트는 역할을 가리지 않는다 — 초기화당한 관리자도 먼저 비밀번호를 바꿔야 한다."""
    await _login_must_change(client, db_session, "gate-admin@example.com", role=UserRole.ADMIN)

    resp = await client.get("/api/admin/users")
    assert resp.status_code == 403
    assert resp.json()["code"] == "PASSWORD_CHANGE_REQUIRED"


async def test_me_is_allowed_and_reports_the_flag(client, db_session):
    """프론트가 세션을 복원할 때 강제 변경 상태임을 알 수 있어야 한다."""
    await _login_must_change(client, db_session, "gate-me@example.com")

    resp = await client.get("/api/auth/me")
    assert resp.status_code == 200
    assert resp.json()["must_change_password"] is True


async def test_logout_is_allowed(client, db_session):
    """관리자에게 임시 비밀번호를 다시 물어봐야 하는 사용자가 화면에 갇히지 않아야 한다."""
    await _login_must_change(client, db_session, "gate-logout@example.com")

    resp = await client.post("/api/auth/logout")
    assert resp.status_code == 200


async def test_change_password_is_allowed_and_clears_the_flag(client, db_session):
    user = await _login_must_change(client, db_session, "gate-change@example.com")

    resp = await client.post(
        "/api/auth/change-password",
        json={"current_password": "temp-pw1", "new_password": "brand-new-pw"},
    )
    assert resp.status_code == 200

    from app.db import raw_connection

    conn = await raw_connection(db_session)
    row = await queries.find_by_id(conn, id=user.id)
    assert row["must_change_password"] is False


async def test_apis_reopen_after_the_password_is_changed(client, db_session):
    await _login_must_change(client, db_session, "gate-reopen@example.com")
    assert (await client.get("/api/projects")).status_code == 403

    resp = await client.post(
        "/api/auth/change-password",
        json={"current_password": "temp-pw1", "new_password": "brand-new-pw"},
    )
    assert resp.status_code == 200

    assert (await client.get("/api/projects")).status_code == 200


async def test_reusing_the_temp_password_keeps_the_gate_closed(client, db_session):
    """임시 비밀번호를 그대로 새 비밀번호로 넣어 게이트를 빠져나갈 수는 없다."""
    user = await _login_must_change(client, db_session, "gate-same@example.com")

    resp = await client.post(
        "/api/auth/change-password",
        json={"current_password": "temp-pw1", "new_password": "temp-pw1"},
    )
    assert resp.status_code == 400
    assert resp.json()["code"] == "SAME_PASSWORD"

    from app.db import raw_connection

    conn = await raw_connection(db_session)
    row = await queries.find_by_id(conn, id=user.id)
    assert row["must_change_password"] is True
    assert (await client.get("/api/projects")).status_code == 403


async def test_normal_users_are_not_affected(client, db_session):
    """플래그가 꺼진 사용자에게는 아무 변화가 없다."""
    user = User(
        email="gate-normal@example.com",
        password_hash=hash_password("pw12345"),
        role=UserRole.MEMBER,
        status=UserStatus.ACTIVE,
    )
    db_session.add(user)
    await db_session.commit()

    resp = await client.post(
        "/api/auth/login", json={"email": "gate-normal@example.com", "password": "pw12345"}
    )
    assert resp.status_code == 200
    assert resp.json()["must_change_password"] is False

    assert (await client.get("/api/projects")).status_code == 200
    assert (await client.get("/api/auth/me")).json()["must_change_password"] is False
