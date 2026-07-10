"""add column comments to users table

Revision ID: 3cd856abfd65
Revises: 0ee6a6f4d65d
Create Date: 2026-07-10 11:33:16.841506

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
import sqlmodel


# revision identifiers, used by Alembic.
revision: str = '3cd856abfd65'
down_revision: Union[str, Sequence[str], None] = '0ee6a6f4d65d'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table_comment(
        "users", "사용자 계정 (자율 회원가입 + 관리자 승인)", existing_comment=None
    )
    op.alter_column("users", "id", comment="기본키, BIGINT 자동 증가", existing_type=sa.BIGINT())
    op.alter_column(
        "users", "email", comment="로그인 이메일, UNIQUE", existing_type=sa.VARCHAR()
    )
    op.alter_column(
        "users",
        "password_hash",
        comment="argon2 해시 값 (평문 저장 금지)",
        existing_type=sa.VARCHAR(),
    )
    op.alter_column(
        "users",
        "role",
        comment="권한: member | admin (기본값 member)",
        existing_type=sa.VARCHAR(),
    )
    op.alter_column(
        "users",
        "status",
        comment="가입 상태: pending | active | disabled | rejected (기본값 pending)",
        existing_type=sa.VARCHAR(),
    )
    op.alter_column(
        "users",
        "approved_at",
        comment="관리자가 승인/거절 처리한 일시",
        existing_type=sa.DateTime(),
    )
    op.alter_column(
        "users",
        "approved_by",
        comment="승인/거절한 관리자 (FK: users.id 자기참조)",
        existing_type=sa.BIGINT(),
    )
    op.alter_column(
        "users",
        "created_at",
        comment="생성일시 (로컬 벽시계 시각, Asia/Seoul 기준, timezone 정보 없음)",
        existing_type=sa.DateTime(),
    )
    op.alter_column(
        "users",
        "created_by",
        comment="생성자 (FK: users.id 자기참조) — 자율가입은 NULL",
        existing_type=sa.BIGINT(),
    )
    op.alter_column(
        "users",
        "updated_at",
        comment="수정일시 (로컬 벽시계 시각, 수정 시 갱신)",
        existing_type=sa.DateTime(),
    )
    op.alter_column(
        "users",
        "updated_by",
        comment="수정자 (FK: users.id 자기참조)",
        existing_type=sa.BIGINT(),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.alter_column("users", "id", comment=None, existing_type=sa.BIGINT())
    op.alter_column("users", "email", comment=None, existing_type=sa.VARCHAR())
    op.alter_column("users", "password_hash", comment=None, existing_type=sa.VARCHAR())
    op.alter_column("users", "role", comment=None, existing_type=sa.VARCHAR())
    op.alter_column("users", "status", comment=None, existing_type=sa.VARCHAR())
    op.alter_column("users", "approved_at", comment=None, existing_type=sa.DateTime())
    op.alter_column("users", "approved_by", comment=None, existing_type=sa.BIGINT())
    op.alter_column("users", "created_at", comment=None, existing_type=sa.DateTime())
    op.alter_column("users", "created_by", comment=None, existing_type=sa.BIGINT())
    op.alter_column("users", "updated_at", comment=None, existing_type=sa.DateTime())
    op.alter_column("users", "updated_by", comment=None, existing_type=sa.BIGINT())
    op.drop_table_comment("users", existing_comment="사용자 계정 (자율 회원가입 + 관리자 승인)")
