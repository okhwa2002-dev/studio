"""add must_change_password to users

Revision ID: 64cee60769f7
Revises: 423501b66954
Create Date: 2026-07-30 11:02:34.270922

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
import sqlmodel


# revision identifiers, used by Alembic.
revision: str = '64cee60769f7'
down_revision: Union[str, Sequence[str], None] = '423501b66954'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # server_default='false' 덕분에 기존 행이 있어도 NOT NULL로 한 번에 추가된다
    # (전부 false = 강제 변경 없음). raw SQL insert_user가 이 컬럼을 넘기지 않으므로
    # server_default는 마이그레이션 이후에도 계속 필요하다.
    op.add_column(
        'users',
        sa.Column('must_change_password', sa.Boolean(), server_default='false', nullable=False,
                  comment='관리자 초기화 후 비밀번호 변경 강제 여부 (true=변경 전까지 다른 API 차단)'),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column('users', 'must_change_password')
