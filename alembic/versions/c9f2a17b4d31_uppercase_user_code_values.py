"""uppercase user code values

Revision ID: c9f2a17b4d31
Revises: 6b5040798a90
Create Date: 2026-07-13

users.role / users.status 의 코드값을 소문자에서 대문자로 통일한다.
기본값은 DB가 아니라 앱 계층(SQLModel Field default)에 있으므로 스키마는 바뀌지 않는다.
바꾸는 것은 (1) 기존 데이터 (2) 컬럼 코멘트의 값 표기 뿐이다.
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = 'c9f2a17b4d31'
down_revision: Union[str, Sequence[str], None] = '6b5040798a90'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # upper()는 이미 대문자인 값에 대해 멱등하므로 재실행해도 안전하다.
    op.execute("UPDATE users SET role = upper(role), status = upper(status)")

    op.alter_column(
        "users",
        "role",
        existing_type=sa.VARCHAR(),
        existing_nullable=False,
        comment="권한: MEMBER | ADMIN (기본값 MEMBER)",
        existing_comment="권한: member | admin (기본값 member)",
    )
    op.alter_column(
        "users",
        "status",
        existing_type=sa.VARCHAR(),
        existing_nullable=False,
        comment="가입 상태: PENDING | ACTIVE | DISABLED | REJECTED (기본값 PENDING)",
        existing_comment="가입 상태: pending | active | disabled | rejected (기본값 pending)",
    )


def downgrade() -> None:
    op.alter_column(
        "users",
        "status",
        existing_type=sa.VARCHAR(),
        existing_nullable=False,
        comment="가입 상태: pending | active | disabled | rejected (기본값 pending)",
        existing_comment="가입 상태: PENDING | ACTIVE | DISABLED | REJECTED (기본값 PENDING)",
    )
    op.alter_column(
        "users",
        "role",
        existing_type=sa.VARCHAR(),
        existing_nullable=False,
        comment="권한: member | admin (기본값 member)",
        existing_comment="권한: MEMBER | ADMIN (기본값 MEMBER)",
    )

    op.execute("UPDATE users SET role = lower(role), status = lower(status)")
