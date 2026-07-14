from app.auth.seed_admin import ensure_admin_seeded
from app.constants import UserRole, UserStatus
from app.db import raw_connection
from app.queries import queries


async def test_ensure_admin_seeded_creates_admin_when_missing(db_session):
    conn = await raw_connection(db_session)

    created = await ensure_admin_seeded(conn, "seed-admin@example.com", "seed-pw-12345")
    assert created is True

    row = await queries.find_by_email(conn, email="seed-admin@example.com")
    assert row is not None
    assert row["role"] == UserRole.ADMIN
    assert row["status"] == UserStatus.ACTIVE


async def test_ensure_admin_seeded_is_idempotent(db_session):
    conn = await raw_connection(db_session)

    first = await ensure_admin_seeded(conn, "seed-admin2@example.com", "seed-pw-12345")
    second = await ensure_admin_seeded(conn, "seed-admin2@example.com", "seed-pw-12345")

    assert first is True
    assert second is False


async def test_ensure_admin_seeded_normalizes_email(db_session):
    conn = await raw_connection(db_session)

    created = await ensure_admin_seeded(conn, " Seed-Admin3@Example.com ", "seed-pw-12345")
    assert created is True

    row = await queries.find_by_email(conn, email="seed-admin3@example.com")
    assert row is not None

    second = await ensure_admin_seeded(conn, "seed-admin3@example.com", "seed-pw-12345")
    assert second is False
