"""add user name

Revision ID: ae9fe4100f24
Revises: bf8d239641e9
Create Date: 2026-07-24 13:34:01.206834

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
import sqlmodel


# revision identifiers, used by Alembic.
revision: str = 'ae9fe4100f24'
down_revision: Union[str, Sequence[str], None] = 'bf8d239641e9'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # 기존 행이 있으면 NOT NULL로 바로 추가할 수 없다. 3단계로 나눈다.
    op.add_column(
        'users',
        sa.Column('name', sqlmodel.sql.sqltypes.AutoString(), nullable=True,
                  comment='표시용 이름 (로그인 식별자는 email)'),
    )
    # 백필: dev@bluenmobile.com -> dev. 이메일 전체보다 이름답고 나중에 고치기 쉽다.
    op.execute("UPDATE users SET name = split_part(email, '@', 1)")
    op.alter_column('users', 'name', nullable=False)


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column('users', 'name')
