import pytest
from sqlalchemy.exc import IntegrityError

from app.models.user import User


async def test_user_defaults(db_session):
    user = User(email="a@example.com", password_hash="hashed-value")
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)

    assert isinstance(user.id, int)
    assert user.role == "member"
    assert user.status == "pending"
    assert user.approved_at is None
    assert user.approved_by is None


async def test_user_email_is_unique(db_session):
    db_session.add(User(email="dup@example.com", password_hash="h1"))
    await db_session.commit()

    db_session.add(User(email="dup@example.com", password_hash="h2"))
    with pytest.raises(IntegrityError):
        await db_session.commit()
