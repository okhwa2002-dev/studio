"""add soft delete to projects

Revision ID: dc4cc6d7949d
Revises: 64cee60769f7
Create Date: 2026-07-30 13:52:28.253916

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
import sqlmodel


# revision identifiers, used by Alembic.
revision: str = 'dc4cc6d7949d'
down_revision: Union[str, Sequence[str], None] = '64cee60769f7'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# 다른 테이블의 FK는 모두 테이블 생성 시 인라인으로 만들어져 Postgres가 자동으로
# {테이블}_{컬럼}_fkey로 이름을 붙였다(faqs_deleted_by_fkey 등). 여기서도 같은 이름을
# 명시한다 — autogenerate가 남긴 None을 그대로 두면 downgrade의 drop_constraint가
# 지울 대상을 찾지 못해 실패한다.
_DELETED_BY_FK = "projects_deleted_by_fkey"


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column(
        'projects',
        sa.Column('deleted_at', sa.DateTime(), nullable=True,
                  comment='소프트 삭제 일시 (NULL=미삭제)'),
    )
    op.add_column(
        'projects',
        sa.Column('deleted_by', sa.BigInteger(), nullable=True,
                  comment='삭제한 사용자 (FK: users.id)'),
    )
    op.create_foreign_key(_DELETED_BY_FK, 'projects', 'users', ['deleted_by'], ['id'])


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_constraint(_DELETED_BY_FK, 'projects', type_='foreignkey')
    op.drop_column('projects', 'deleted_by')
    op.drop_column('projects', 'deleted_at')
