from sqlalchemy import text


async def test_session_connects(db_session):
    result = await db_session.execute(text("SELECT 1"))
    assert result.scalar_one() == 1
