"""add queued stage status

Revision ID: bf8d239641e9
Revises: e716148755d5
Create Date: 2026-07-21 15:39:51.981849

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
import sqlmodel


# revision identifiers, used by Alembic.
revision: str = 'bf8d239641e9'
down_revision: Union[str, Sequence[str], None] = 'e716148755d5'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.alter_column(
        "stages",
        "status",
        comment="상태: PENDING|QUEUED|RUNNING|NEEDS_REVIEW|APPROVED|FAILED",
        existing_type=sa.VARCHAR(),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.alter_column(
        "stages",
        "status",
        comment="상태: PENDING|RUNNING|NEEDS_REVIEW|APPROVED|FAILED",
        existing_type=sa.VARCHAR(),
    )
