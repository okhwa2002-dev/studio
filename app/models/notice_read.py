from datetime import datetime
from typing import Optional

from sqlalchemy import BigInteger, UniqueConstraint
from sqlmodel import Field

from app.models.base import (
    BaseEntity,
    created_at_field,
    created_by_field,
    updated_at_field,
    updated_by_field,
)


class NoticeRead(BaseEntity, table=True):
    """공지 읽음 기록.

    read_at 컬럼을 따로 두지 않는다 — 행의 존재가 곧 '읽음'이고, 읽은 시각은
    created_at이다. read_at을 두면 항상 created_at과 같은 값이 들어가는
    중복 컬럼이 된다.
    """

    __tablename__ = "notice_reads"
    __table_args__ = (
        UniqueConstraint("notice_id", "user_id", name="uq_notice_reads_notice_user"),
        {"comment": "공지 읽음 기록 (행 존재 = 읽음, created_at = 읽은 시각)"},
    )

    notice_id: int = Field(
        sa_type=BigInteger,
        foreign_key="notices.id",
        index=True,
        sa_column_kwargs={"comment": "읽은 공지 (FK: notices.id)"},
    )
    user_id: int = Field(
        sa_type=BigInteger,
        foreign_key="users.id",
        index=True,
        sa_column_kwargs={"comment": "읽은 사용자 (FK: users.id)"},
    )

    created_at: Optional[datetime] = created_at_field()
    # created_by/updated_by에는 user_id와 같은 값(읽은 본인)이 들어간다.
    created_by: Optional[int] = created_by_field(foreign_key="users.id")
    updated_at: Optional[datetime] = updated_at_field()
    updated_by: Optional[int] = updated_by_field(foreign_key="users.id")
