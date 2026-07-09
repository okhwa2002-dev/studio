from sqlalchemy import text


async def test_error_codes_table_exists(db_session):
    # 테이블에 행을 넣고 다시 읽을 수 있어야 한다
    await db_session.execute(
        text(
            "INSERT INTO error_codes (code, message, http_status, is_default, is_active, created_at, updated_at) "
            "VALUES (:c, :m, :s, :d, :a, now(), now())"
        ),
        {"c": "TEST_CODE", "m": "테스트", "s": 400, "d": False, "a": True},
    )
    row = (await db_session.execute(
        text("SELECT code, message, http_status FROM error_codes WHERE code = :c"),
        {"c": "TEST_CODE"},
    )).one()
    assert row.code == "TEST_CODE"
    assert row.http_status == 400
