"""create faqs

Revision ID: 423501b66954
Revises: 0387c54489e8
Create Date: 2026-07-29 16:26:46.446640

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '423501b66954'
down_revision: Union[str, Sequence[str], None] = '0387c54489e8'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        "faqs",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False,
                  comment="기본키, BIGINT 자동 증가"),
        sa.Column("question", sa.String(), nullable=False, comment="질문"),
        sa.Column("answer", sa.Text(), nullable=False,
                  comment="답변 (일반 텍스트, 줄바꿈 그대로 표시)"),
        sa.Column("category", sa.String(), nullable=False,
                  comment="분류: ACCOUNT | PROJECT | PRODUCTION | ETC"),
        sa.Column("status", sa.String(), nullable=False,
                  comment="상태: DRAFT | PUBLISHED (기본값 DRAFT)"),
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default="0",
                  comment="목록 정렬 순서 (작을수록 위)"),
        sa.Column("deleted_at", sa.DateTime(), nullable=True,
                  comment="소프트 삭제 일시 (NULL=미삭제)"),
        sa.Column("deleted_by", sa.BigInteger(), nullable=True,
                  comment="삭제한 관리자 (FK: users.id)"),
        sa.Column("created_at", sa.DateTime(), nullable=False,
                  server_default=sa.func.timezone("Asia/Seoul", sa.func.now()),
                  comment="생성일시 (로컬 벽시계 시각, Asia/Seoul 기준, timezone 정보 없음)"),
        sa.Column("created_by", sa.BigInteger(), nullable=True, comment="생성자"),
        sa.Column("updated_at", sa.DateTime(), nullable=False,
                  server_default=sa.func.timezone("Asia/Seoul", sa.func.now()),
                  comment="수정일시 (로컬 벽시계 시각, 수정 시 갱신)"),
        sa.Column("updated_by", sa.BigInteger(), nullable=True, comment="수정자"),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["deleted_by"], ["users.id"]),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"]),
        sa.ForeignKeyConstraint(["updated_by"], ["users.id"]),
        comment="자주 묻는 질문 (관리자 작성, 전체 사용자 열람)",
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_table("faqs")
