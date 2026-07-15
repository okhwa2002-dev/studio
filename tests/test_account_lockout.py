from app.auth.security import hash_password
from app.constants import UserStatus
from app.db import raw_connection
from app.models.user import User
from app.queries import queries


async def test_new_user_lock_fields_default(db_session):
    user = User(email="lockdefault@example.com", password_hash=hash_password("pw12345"))
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    assert user.failed_login_count == 0
    assert user.locked_at is None
    assert user.unlocked_at is None


async def test_find_by_email_returns_lock_fields(db_session):
    # 로그인 로직이 읽을 수 있도록 SELECT가 잠금 컬럼을 포함해야 한다.
    user = User(email="lockcols@example.com", password_hash=hash_password("pw12345"), status=UserStatus.ACTIVE)
    db_session.add(user)
    await db_session.commit()
    conn = await raw_connection(db_session)
    row = await queries.find_by_email(conn, email="lockcols@example.com")
    assert "failed_login_count" in row
    assert "locked_at" in row
    assert "unlocked_at" in row
