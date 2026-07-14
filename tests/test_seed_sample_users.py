from app.auth.seed_sample_users import (
    SAMPLE_PASSWORD,
    SAMPLE_USERS,
    ensure_sample_users_seeded,
    is_local_database,
)
from app.constants import UserStatus
from app.db import raw_connection
from app.queries import queries
from app.utils.time import now_local


async def _count_by_status(conn, status: UserStatus) -> int:
    return len([row async for row in queries.list_by_status(conn, status=status)])


async def test_seeds_eight_sample_users(db_session):
    conn = await raw_connection(db_session)

    created = await ensure_sample_users_seeded(conn)
    assert created == 8

    assert await _count_by_status(conn, UserStatus.PENDING) == 5
    assert await _count_by_status(conn, UserStatus.ACTIVE) == 2
    assert await _count_by_status(conn, UserStatus.REJECTED) == 1


async def test_seeding_is_idempotent(db_session):
    conn = await raw_connection(db_session)

    first = await ensure_sample_users_seeded(conn)
    second = await ensure_sample_users_seeded(conn)

    assert first == len(SAMPLE_USERS)
    assert second == 0


async def test_active_sample_user_can_log_in(client, db_session):
    # 소스에 적힌 비밀번호가 실제로 로그인에 통하는지 확인한다.
    # (해시를 잘못 만들면 시드는 성공하지만 아무도 로그인하지 못한다.)
    conn = await raw_connection(db_session)
    await ensure_sample_users_seeded(conn)
    await db_session.commit()

    resp = await client.post(
        "/auth/login",
        json={"email": "sample-member1@example.com", "password": SAMPLE_PASSWORD},
    )
    assert resp.status_code == 200


async def test_pending_sample_user_cannot_log_in(client, db_session):
    conn = await raw_connection(db_session)
    await ensure_sample_users_seeded(conn)
    await db_session.commit()

    resp = await client.post(
        "/auth/login",
        json={"email": "sample-pending1@example.com", "password": SAMPLE_PASSWORD},
    )
    assert resp.status_code == 403


async def test_reseed_does_not_revert_approved_sample_user(db_session):
    # 모듈 docstring의 약속: 관리자가 이미 승인해 둔 샘플 계정은 재시드로도
    # 상태가 되돌아가지 않는다. 이 테스트가 없으면 "재시드 시 상태 초기화"
    # 같은 미래의 변경이 이 약속을 조용히 깨도 아무도 알아채지 못한다.
    conn = await raw_connection(db_session)
    await ensure_sample_users_seeded(conn)

    pending = await queries.find_by_email(conn, email="sample-pending1@example.com")
    now = now_local()
    await queries.update_status(
        conn,
        id=pending["id"],
        status=UserStatus.ACTIVE,
        approved_at=now,
        approved_by=pending["id"],
        updated_at=now,
        updated_by=pending["id"],
    )
    await db_session.commit()

    second = await ensure_sample_users_seeded(conn)
    assert second == 0

    approved = await queries.find_by_email(conn, email="sample-pending1@example.com")
    assert approved["status"] == UserStatus.ACTIVE


def test_is_local_database_accepts_local_hosts():
    assert is_local_database("postgresql+asyncpg://studio:studio@localhost:5437/studio") is True
    assert is_local_database("postgresql+asyncpg://studio:studio@127.0.0.1:5437/studio") is True


def test_is_local_database_rejects_remote_hosts():
    assert is_local_database("postgresql+asyncpg://studio:studio@db.example.com:5432/studio") is False
    # 문자열 포함 검사("localhost" in url)로 구현하면 아래에서 걸린다 — 호스트명을 파싱해야 한다.
    assert is_local_database("postgresql+asyncpg://studio:studio@db.localhost.evil.com:5432/studio") is False
