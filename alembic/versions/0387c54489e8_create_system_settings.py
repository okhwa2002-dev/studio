"""create system_settings

Revision ID: 0387c54489e8
Revises: c6d1293bd755
Create Date: 2026-07-29 09:22:12.642750

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
import sqlmodel


# revision identifiers, used by Alembic.
revision: str = '0387c54489e8'
down_revision: Union[str, Sequence[str], None] = 'c6d1293bd755'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        "system_settings",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False,
                  comment="기본키, BIGINT 자동 증가"),
        sa.Column("key", sa.String(), nullable=False,
                  comment="설정 키 (RuntimeSettings 필드명)"),
        sa.Column("value", sa.Text(), nullable=False,
                  comment="설정값 (JSON 직렬화 문자열)"),
        sa.Column("created_at", sa.DateTime(), nullable=False,
                  server_default=sa.func.timezone("Asia/Seoul", sa.func.now()),
                  comment="생성일시 (로컬 벽시계 시각, Asia/Seoul 기준, timezone 정보 없음)"),
        sa.Column("created_by", sa.BigInteger(), nullable=True, comment="생성자"),
        sa.Column("updated_at", sa.DateTime(), nullable=False,
                  server_default=sa.func.timezone("Asia/Seoul", sa.func.now()),
                  comment="수정일시 (로컬 벽시계 시각, 수정 시 갱신)"),
        sa.Column("updated_by", sa.BigInteger(), nullable=True, comment="수정자"),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"]),
        sa.ForeignKeyConstraint(["updated_by"], ["users.id"]),
        sa.UniqueConstraint("key"),
        comment="시스템 설정 (관리자가 기본값에서 바꾼 항목만 저장)",
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_table("system_settings")
