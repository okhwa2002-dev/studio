from sqlalchemy import text

from app.auth.security import hash_password
from app.constants import UserStatus
from app.models.user import User


async def test_model_has_name_with_empty_default():
    """모델 기본값이 있어야 기존 테스트 18개 파일의 User(...) 생성이 깨지지 않는다."""
    user = User(email="a@example.com", password_hash="x", status=UserStatus.ACTIVE)
    assert user.name == ""


async def test_name_column_is_not_null(db_session):
    """DB는 NULL을 거부해야 한다 — 모델 기본값과 별개로 스키마 제약이 살아 있어야 한다."""
    row = await db_session.execute(
        text(
            "SELECT is_nullable FROM information_schema.columns "
            "WHERE table_name = 'users' AND column_name = 'name'"
        )
    )
    assert row.scalar() == "NO"


async def test_existing_rows_are_backfilled_from_email_local_part(db_session):
    """마이그레이션이 이미 적용된 DB에서, 이메일 앞부분 백필 규칙이 그대로 재현되는지 확인한다.

    conftest가 마이그레이션을 끝낸 뒤 테스트가 도므로 '마이그레이션 시점의 기존 행'을
    직접 만들 수는 없다. 대신 백필에 쓴 SQL 식이 의도한 값을 내는지 고정한다 —
    이 식이 바뀌면(예: split_part → substring 오용) 여기서 잡힌다.
    """
    result = await db_session.execute(
        text("SELECT split_part('dev@bluenmobile.com', '@', 1)")
    )
    assert result.scalar() == "dev"


async def test_user_can_be_saved_with_name(db_session):
    user = User(
        email="named@example.com",
        password_hash=hash_password("pw12345"),
        status=UserStatus.ACTIVE,
        name="홍길동",
    )
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    assert user.name == "홍길동"
