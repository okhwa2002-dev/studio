"""add account lockout columns

Revision ID: 9cb1c3452965
Revises: c9f2a17b4d31
Create Date: 2026-07-15 13:30:09.544191

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
import sqlmodel


# revision identifiers, used by Alembic.
revision: str = '9cb1c3452965'
down_revision: Union[str, Sequence[str], None] = 'c9f2a17b4d31'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column('users', sa.Column('failed_login_count', sa.Integer(), nullable=False, server_default='0', comment='연속 로그인 실패 횟수 (성공 시 0으로 리셋)'))
    op.add_column('users', sa.Column('locked_at', sa.DateTime(), nullable=True, comment='계정 잠긴 시각 (NULL=안 잠김, 값 있음=잠김)'))
    op.add_column('users', sa.Column('unlocked_at', sa.DateTime(), nullable=True, comment='관리자가 잠금 해제한 시각 (해제일시)'))


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column('users', 'unlocked_at')
    op.drop_column('users', 'locked_at')
    op.drop_column('users', 'failed_login_count')
