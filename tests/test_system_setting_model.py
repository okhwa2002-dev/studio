import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from app.models.system_setting import SystemSetting


async def test_can_insert_and_read_setting(db_session):
    db_session.add(SystemSetting(key="render_font_size", value="42"))
    await db_session.commit()

    row = await db_session.execute(
        text("SELECT key, value FROM system_settings WHERE key = 'render_font_size'")
    )
    assert row.one() == ("render_font_size", "42")


async def test_key_is_unique(db_session):
    db_session.add(SystemSetting(key="whisper_model", value='"small"'))
    await db_session.commit()

    db_session.add(SystemSetting(key="whisper_model", value='"medium"'))
    with pytest.raises(IntegrityError):
        await db_session.commit()


async def test_audit_columns_are_filled_by_db_default(db_session):
    """created_at/updated_at은 서버 기본값으로 채워진다 — 앱이 안 넣어도 NOT NULL을 만족한다."""
    db_session.add(SystemSetting(key="stock_timeout_sec", value="60"))
    await db_session.commit()

    row = await db_session.execute(
        text("SELECT created_at, updated_at FROM system_settings WHERE key = 'stock_timeout_sec'")
    )
    created_at, updated_at = row.one()
    assert created_at is not None
    assert updated_at is not None


async def test_column_order_is_id_business_audit(db_session):
    """테이블 생성 규칙: id → 업무 컬럼 → 감사 컬럼."""
    row = await db_session.execute(
        text(
            "SELECT column_name FROM information_schema.columns "
            "WHERE table_name = 'system_settings' ORDER BY ordinal_position"
        )
    )
    assert [r[0] for r in row] == [
        "id", "key", "value", "created_at", "created_by", "updated_at", "updated_by",
    ]
