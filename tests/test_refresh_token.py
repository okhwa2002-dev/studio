from datetime import timedelta

from sqlalchemy import BigInteger

from app.db import raw_connection
from app.models.refresh_token import RefreshToken
from app.models.user import User
from app.queries import queries
from app.utils.time import now_local


async def _make_user(db_session, email: str) -> User:
    user = User(email=email, password_hash="hashed-value")
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    return user


async def test_refresh_token_model_defaults(db_session):
    user = await _make_user(db_session, "rt-model@example.com")

    token = RefreshToken(
        user_id=user.id, token_hash="model-hash-1", expires_at=now_local() + timedelta(days=14)
    )
    db_session.add(token)
    await db_session.commit()
    await db_session.refresh(token)

    assert isinstance(token.id, int)
    assert token.revoked_at is None


async def test_insert_and_find_refresh_token_by_hash(db_session):
    user = await _make_user(db_session, "rt-query@example.com")
    conn = await raw_connection(db_session)
    now = now_local()

    token_id = await queries.insert_refresh_token(
        conn,
        user_id=user.id,
        token_hash="query-hash-1",
        expires_at=now + timedelta(days=14),
        created_at=now,
        updated_at=now,
    )
    assert isinstance(token_id, int)

    row = await queries.find_by_token_hash(conn, token_hash="query-hash-1")
    assert row["user_id"] == user.id
    assert row["revoked_at"] is None


async def test_revoke_by_id_marks_token_revoked(db_session):
    user = await _make_user(db_session, "rt-revoke@example.com")
    conn = await raw_connection(db_session)
    now = now_local()

    token_id = await queries.insert_refresh_token(
        conn,
        user_id=user.id,
        token_hash="revoke-hash-1",
        expires_at=now + timedelta(days=14),
        created_at=now,
        updated_at=now,
    )

    await queries.revoke_by_id(conn, id=token_id, revoked_at=now, updated_at=now)

    row = await queries.find_by_token_hash(conn, token_hash="revoke-hash-1")
    assert row["revoked_at"] is not None


async def test_revoke_all_for_user_revokes_every_active_token(db_session):
    user = await _make_user(db_session, "rt-revoke-all@example.com")
    conn = await raw_connection(db_session)
    now = now_local()

    await queries.insert_refresh_token(
        conn, user_id=user.id, token_hash="all-hash-1",
        expires_at=now + timedelta(days=14), created_at=now, updated_at=now,
    )
    await queries.insert_refresh_token(
        conn, user_id=user.id, token_hash="all-hash-2",
        expires_at=now + timedelta(days=14), created_at=now, updated_at=now,
    )

    await queries.revoke_all_for_user(conn, user_id=user.id, revoked_at=now, updated_at=now)

    row1 = await queries.find_by_token_hash(conn, token_hash="all-hash-1")
    row2 = await queries.find_by_token_hash(conn, token_hash="all-hash-2")
    assert row1["revoked_at"] is not None
    assert row2["revoked_at"] is not None


def test_user_id_is_bigint_matching_users_pk():
    # user_id는 users.id(BIGINT)를 참조하는 FK이므로, 컬럼 타입도 BIGINT여야 한다
    # (Integer로 두면 21억을 넘는 id를 참조 못 함 — app/models/base.py의
    # created_by/updated_by와 동일한 규칙, tests/test_base_entity.py 참고).
    table = RefreshToken.__table__
    assert isinstance(table.c.user_id.type, BigInteger)
