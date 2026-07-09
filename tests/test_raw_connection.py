from app.db import raw_connection


async def test_raw_connection_returns_live_asyncpg_connection(db_session):
    conn = await raw_connection(db_session)

    # asyncpg.Connection에는 fetchval 같은 메서드가 있어야 한다(raw 드라이버 커넥션 확인).
    value = await conn.fetchval("SELECT 1")
    assert value == 1


async def test_raw_connection_shares_transaction_with_session(db_session):
    # ORM 세션에서 커밋 전에 넣은(아직 flush만 된) 데이터를, 같은 트랜잭션을 공유하는
    # raw 커넥션에서도 볼 수 있어야 한다(SAVEPOINT 격리가 raw 커넥션에도 적용됨).
    from app.models.error_code import ErrorCode

    db_session.add(ErrorCode(code="RAW_CONN_CHECK", message="m", http_status=400))
    await db_session.flush()

    conn = await raw_connection(db_session)
    row = await conn.fetchrow("SELECT code FROM error_codes WHERE code = $1", "RAW_CONN_CHECK")

    assert row is not None
    assert row["code"] == "RAW_CONN_CHECK"
