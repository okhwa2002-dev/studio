import json

from app.constants import UserStatus
from app.db import raw_connection
from app.queries import queries
from app.runtime_settings import invalidate_runtime_settings
from app.utils.time import now_local


async def _enable_auto_approve(db_session) -> None:
    conn = await raw_connection(db_session)
    await queries.upsert_setting(
        conn, key="signup_auto_approve", value=json.dumps(True),
        now=now_local(), actor_id=None,
    )
    invalidate_runtime_settings()


async def test_register_is_pending_by_default(client):
    resp = await client.post(
        "/api/auth/register",
        json={"email": "default-pending@example.com", "password": "pw123456", "name": "홍길동"},
    )
    assert resp.status_code == 201
    assert resp.json()["status"] == UserStatus.PENDING


async def test_register_is_active_when_auto_approve_is_on(client, db_session):
    await _enable_auto_approve(db_session)

    resp = await client.post(
        "/api/auth/register",
        json={"email": "auto-active@example.com", "password": "pw123456", "name": "홍길동"},
    )
    assert resp.status_code == 201
    assert resp.json()["status"] == UserStatus.ACTIVE


async def test_auto_approved_user_can_log_in_immediately(client, db_session):
    await _enable_auto_approve(db_session)
    await client.post(
        "/api/auth/register",
        json={"email": "auto-login@example.com", "password": "pw123456", "name": "홍길동"},
    )

    resp = await client.post(
        "/api/auth/login",
        json={"email": "auto-login@example.com", "password": "pw123456"},
    )
    assert resp.status_code == 200


async def test_existing_pending_user_is_not_auto_approved(client, db_session):
    """설정은 이후 가입에만 적용된다. 대기 중인 사용자는 관리자가 처리한다."""
    await client.post(
        "/api/auth/register",
        json={"email": "already-pending@example.com", "password": "pw123456", "name": "홍길동"},
    )
    await _enable_auto_approve(db_session)

    from sqlalchemy import text

    row = await db_session.execute(
        text("SELECT status FROM users WHERE email = 'already-pending@example.com'")
    )
    assert row.scalar() == UserStatus.PENDING
