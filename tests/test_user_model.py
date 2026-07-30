import pytest
from sqlalchemy.exc import IntegrityError

from app.constants import UserRole, UserStatus
from app.models.user import User


async def test_user_defaults(db_session):
    user = User(email="a@example.com", password_hash="hashed-value")
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)

    assert isinstance(user.id, int)
    assert user.role == UserRole.MEMBER
    assert user.status == UserStatus.PENDING
    assert user.approved_at is None
    assert user.approved_by is None
    # 관리자 초기화 전에는 강제 변경이 걸려 있지 않다.
    assert user.must_change_password is False


async def test_user_email_is_unique(db_session):
    db_session.add(User(email="dup@example.com", password_hash="h1"))
    await db_session.commit()

    db_session.add(User(email="dup@example.com", password_hash="h2"))
    with pytest.raises(IntegrityError):
        await db_session.commit()
