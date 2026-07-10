from sqlmodel import Field

from app.db import raw_connection
from app.models.base import BaseEntity


class _RawConnSample(BaseEntity, table=True):
    __tablename__ = "raw_conn_sample"
    name: str = Field()


async def test_raw_connection_returns_live_asyncpg_connection(db_session):
    conn = await raw_connection(db_session)

    # asyncpg.Connection에는 fetchval 같은 메서드가 있어야 한다(raw 드라이버 커넥션 확인).
    value = await conn.fetchval("SELECT 1")
    assert value == 1


async def test_raw_connection_shares_transaction_with_session(db_session):
    # ORM 세션에서 커밋 전에 넣은(아직 flush만 된) 데이터를, 같은 트랜잭션을 공유하는
    # raw 커넥션에서도 볼 수 있어야 한다(SAVEPOINT 격리가 raw 커넥션에도 적용됨).
    db_session.add(_RawConnSample(name="raw-conn-check"))
    await db_session.flush()

    conn = await raw_connection(db_session)
    row = await conn.fetchrow(
        "SELECT name FROM raw_conn_sample WHERE name = $1", "raw-conn-check"
    )

    assert row is not None
    assert row["name"] == "raw-conn-check"
