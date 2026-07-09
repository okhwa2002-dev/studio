"""store timestamps as local naive time

Revision ID: 621184be641b
Revises: 6a0fb178c5b7
Create Date: 2026-07-09 16:52:53.427658

"""
from typing import Sequence, Union

from alembic import op

from app.config import get_settings

# revision identifiers, used by Alembic.
revision: str = '621184be641b'
down_revision: Union[str, Sequence[str], None] = '6a0fb178c5b7'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema.

    created_at/updated_at를 TIMESTAMPTZ(UTC 저장)에서 naive TIMESTAMP(로컬
    벽시계 시각 저장)로 변경한다. 기존 값은 USING 절로 APP_TIMEZONE 기준
    벽시계 시각으로 변환하여 보존한다.
    """
    tz = get_settings().app_timezone
    op.execute(
        f"ALTER TABLE error_codes "
        f"ALTER COLUMN created_at TYPE TIMESTAMP USING (created_at AT TIME ZONE '{tz}'), "
        f"ALTER COLUMN created_at DROP DEFAULT"
    )
    op.execute(
        f"ALTER TABLE error_codes "
        f"ALTER COLUMN updated_at TYPE TIMESTAMP USING (updated_at AT TIME ZONE '{tz}'), "
        f"ALTER COLUMN updated_at DROP DEFAULT"
    )


def downgrade() -> None:
    """Downgrade schema."""
    tz = get_settings().app_timezone
    op.execute(
        f"ALTER TABLE error_codes "
        f"ALTER COLUMN created_at TYPE TIMESTAMPTZ USING (created_at AT TIME ZONE '{tz}'), "
        f"ALTER COLUMN created_at SET DEFAULT now()"
    )
    op.execute(
        f"ALTER TABLE error_codes "
        f"ALTER COLUMN updated_at TYPE TIMESTAMPTZ USING (updated_at AT TIME ZONE '{tz}'), "
        f"ALTER COLUMN updated_at SET DEFAULT now()"
    )
