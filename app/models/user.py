from datetime import datetime
from typing import Optional

from sqlalchemy import BigInteger
from sqlmodel import Field

from app.models.base import (
    BaseEntity,
    created_at_field,
    created_by_field,
    updated_at_field,
    updated_by_field,
)


class User(BaseEntity, table=True):
    __tablename__ = "users"
    __table_args__ = {"comment": "사용자 계정 (자율 회원가입 + 관리자 승인)"}

    email: str = Field(
        unique=True, index=True, sa_column_kwargs={"comment": "로그인 이메일, UNIQUE"}
    )
    password_hash: str = Field(
        sa_column_kwargs={"comment": "argon2 해시 값 (평문 저장 금지)"}
    )
    role: str = Field(
        default="member",
        sa_column_kwargs={"comment": "권한: member | admin (기본값 member)"},
    )
    status: str = Field(
        default="pending",
        sa_column_kwargs={
            "comment": "가입 상태: pending | active | disabled | rejected (기본값 pending)"
        },
    )
    approved_at: Optional[datetime] = Field(
        default=None, sa_column_kwargs={"comment": "관리자가 승인/거절 처리한 일시"}
    )
    approved_by: Optional[int] = Field(
        default=None,
        sa_type=BigInteger,
        foreign_key="users.id",
        nullable=True,
        sa_column_kwargs={"comment": "승인/거절한 관리자 (FK: users.id 자기참조)"},
    )

    created_at: Optional[datetime] = created_at_field()
    created_by: Optional[int] = created_by_field(
        foreign_key="users.id", comment="생성자 (FK: users.id 자기참조) — 자율가입은 NULL"
    )
    updated_at: Optional[datetime] = updated_at_field()
    updated_by: Optional[int] = updated_by_field(
        foreign_key="users.id", comment="수정자 (FK: users.id 자기참조)"
    )
