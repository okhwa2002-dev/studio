from app.auth.security import hash_password, hash_refresh_token
from app.constants import UserRole, UserStatus
from app.db import raw_connection
from app.models.user import User
from app.queries import queries

_PW = "pw12345678"  # 8자 이상


async def _register_and_login(client, db_session, email: str = "cp@example.com") -> User:
    user = User(email=email, password_hash=hash_password(_PW),
                role=UserRole.MEMBER, status=UserStatus.ACTIVE, name="홍길동")
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    resp = await client.post("/api/auth/login", json={"email": email, "password": _PW})
    assert resp.status_code == 200
    return user


async def test_change_password_requires_auth(client):
    resp = await client.post("/api/auth/change-password",
                             json={"current_password": _PW, "new_password": "newpw12345"})
    assert resp.status_code == 401


async def test_change_password_success_and_relogin(client, db_session):
    await _register_and_login(client, db_session, "cp-ok@example.com")
    resp = await client.post("/api/auth/change-password",
                             json={"current_password": _PW, "new_password": "newpw12345"})
    assert resp.status_code == 200

    # 예전 비밀번호로는 로그인 불가, 새 비밀번호로는 가능해야 한다.
    old = await client.post("/api/auth/login", json={"email": "cp-ok@example.com", "password": _PW})
    assert old.status_code == 401
    new = await client.post("/api/auth/login",
                            json={"email": "cp-ok@example.com", "password": "newpw12345"})
    assert new.status_code == 200


async def test_change_password_wrong_current(client, db_session):
    await _register_and_login(client, db_session, "cp-wrong@example.com")
    resp = await client.post("/api/auth/change-password",
                             json={"current_password": "wrongpw123", "new_password": "newpw12345"})
    assert resp.status_code == 400
    assert resp.json()["code"] == "INVALID_PASSWORD"


async def test_change_password_too_short(client, db_session):
    await _register_and_login(client, db_session, "cp-short@example.com")
    resp = await client.post("/api/auth/change-password",
                             json={"current_password": _PW, "new_password": "short"})
    assert resp.status_code == 400
    assert resp.json()["code"] == "WEAK_PASSWORD"


async def test_change_password_same_as_current(client, db_session):
    await _register_and_login(client, db_session, "cp-same@example.com")
    resp = await client.post("/api/auth/change-password",
                             json={"current_password": _PW, "new_password": _PW})
    assert resp.status_code == 400
    assert resp.json()["code"] == "SAME_PASSWORD"


async def test_change_password_revokes_other_sessions(client, db_session):
    # 세션 A로 로그인해 토큰을 챙겨두고, 세션 B로 다시 로그인한 뒤 B에서 비밀번호를 바꾼다.
    await _register_and_login(client, db_session, "cp-multi@example.com")
    token_a = client.cookies.get("refresh_token")

    relog = await client.post("/api/auth/login",
                              json={"email": "cp-multi@example.com", "password": _PW})
    assert relog.status_code == 200  # 이제 client는 세션 B 쿠키를 들고 있다

    changed = await client.post("/api/auth/change-password",
                                json={"current_password": _PW, "new_password": "newpw12345"})
    assert changed.status_code == 200

    # 다른 기기(세션 A)의 리프레시 토큰은 DB에서 폐기(revoked_at 설정)돼야 한다.
    conn = await raw_connection(db_session)
    row = await queries.find_by_token_hash(conn, token_hash=hash_refresh_token(token_a))
    assert row is not None and row["revoked_at"] is not None
