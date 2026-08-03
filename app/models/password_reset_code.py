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


class PasswordResetCode(BaseEntity, table=True):
    __tablename__ = "password_reset_codes"
    __table_args__ = {"comment": "비밀번호 재설정 인증코드 (평문 저장, 1회용, 만료)"}

    user_id: int = Field(
        sa_type=BigInteger,
        foreign_key="users.id",
        index=True,
        sa_column_kwargs={"comment": "코드 소유자 (FK: users.id)"},
    )
    code: str = Field(
        sa_column_kwargs={"comment": "6자리 인증코드(000000~999999) 문자열. 앞자리 0 보존, 해시 안 함"},
    )
    expires_at: datetime = Field(sa_column_kwargs={"comment": "만료 일시 (발급 + 10분)"})
    consumed_at: Optional[datetime] = Field(
        default=None,
        sa_column_kwargs={"comment": "사용 완료 일시 (1회용). NULL이면 미사용"},
    )
    attempts: int = Field(
        default=0,
        sa_column_kwargs={
            "server_default": "0",
            "comment": "검증 실패 누적. 한도 초과 시 코드 무효화",
        },
    )

    created_at: Optional[datetime] = created_at_field()
    created_by: Optional[int] = created_by_field()
    updated_at: Optional[datetime] = updated_at_field()
    updated_by: Optional[int] = updated_by_field()
