from datetime import timedelta

from app.db import raw_connection
from app.models.user import User
from app.queries import queries
from app.utils.time import now_local


async def _make_user(db_session, email="reset-model@example.com") -> int:
    user = User(email=email, password_hash="x", name="테스트", role="MEMBER", status="ACTIVE")
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    return user.id


async def test_insert_and_find_active_reset_code(db_session):
    user_id = await _make_user(db_session)
    conn = await raw_connection(db_session)
    now = now_local()

    code_id = await queries.insert_reset_code(
        conn,
        user_id=user_id,
        code="123456",
        expires_at=now + timedelta(minutes=10),
        created_at=now,
        updated_at=now,
    )
    assert isinstance(code_id, int)

    row = await queries.find_active_reset_code(conn, user_id=user_id)
    assert row is not None
    assert row["code"] == "123456"
    assert row["attempts"] == 0
    assert row["consumed_at"] is None


async def test_consumed_code_is_not_active(db_session):
    user_id = await _make_user(db_session, "reset-model2@example.com")
    conn = await raw_connection(db_session)
    now = now_local()
    code_id = await queries.insert_reset_code(
        conn,
        user_id=user_id,
        code="234567",
        expires_at=now + timedelta(minutes=10),
        created_at=now,
        updated_at=now,
    )

    await queries.consume_reset_code(conn, id=code_id, consumed_at=now, updated_at=now)

    assert await queries.find_active_reset_code(conn, user_id=user_id) is None
