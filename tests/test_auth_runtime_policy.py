import json

from app.auth.security import hash_password
from app.constants import UserRole, UserStatus
from app.db import raw_connection
from app.models.user import User
from app.queries import queries
from app.runtime_settings import invalidate_runtime_settings
from app.utils.time import now_local

PASSWORD = "pw12345678"


async def _override(db_session, key: str, value) -> None:
    conn = await raw_connection(db_session)
    await queries.upsert_setting(
        conn, key=key, value=json.dumps(value), now=now_local(), actor_id=None
    )
    invalidate_runtime_settings()


async def _user(db_session, email: str) -> User:
    user = User(
        email=email,
        password_hash=hash_password(PASSWORD),
        role=UserRole.MEMBER,
        status=UserStatus.ACTIVE,
        name="사용자",
    )
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    return user


async def test_lockout_threshold_follows_runtime_setting(client, db_session):
    """잠금 횟수를 2로 낮추면 두 번째 실패에서 잠긴다."""
    user = await _user(db_session, "lock-runtime@example.com")
    await _override(db_session, "failed_login_limit", 2)

    for _ in range(2):
        resp = await client.post(
            "/api/auth/login", json={"email": user.email, "password": "wrong-password"}
        )
        assert resp.status_code == 401

    # 이제 올바른 비밀번호를 넣어도 잠김이다
    resp = await client.post(
        "/api/auth/login", json={"email": user.email, "password": PASSWORD}
    )
    assert resp.status_code == 423
    assert resp.json()["code"] == "ACCOUNT_LOCKED"


async def test_change_password_min_length_follows_runtime_setting(client, db_session):
    user = await _user(db_session, "minlen-runtime@example.com")
    await client.post("/api/auth/login", json={"email": user.email, "password": PASSWORD})
    await _override(db_session, "password_min_len", 12)

    resp = await client.post(
        "/api/auth/change-password",
        json={"current_password": PASSWORD, "new_password": "short12345"},   # 10자
    )
    assert resp.status_code == 400
    assert resp.json()["code"] == "WEAK_PASSWORD"

    resp = await client.post(
        "/api/auth/change-password",
        json={"current_password": PASSWORD, "new_password": "longenough123"},  # 13자
    )
    assert resp.status_code == 200
