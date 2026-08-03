from datetime import datetime
from typing import Optional

from sqlmodel import Field

from app.models.base import (
    BaseEntity,
    created_at_field,
    created_by_field,
    updated_at_field,
    updated_by_field,
)


class PasswordResetRequest(BaseEntity, table=True):
    __tablename__ = "password_reset_requests"
    __table_args__ = {"comment": "비밀번호 재설정 요청 이력 (rate limit 판정의 원장)"}

    email: str = Field(
        index=True,
        sa_column_kwargs={
            "comment": "정규화된(strip().lower()) 제출 이메일. 계정 존재와 무관하게 기록",
        },
    )
    client_ip: Optional[str] = Field(
        default=None,
        index=True,
        sa_column_kwargs={
            "comment": "요청자 IP (request.client.host). 알 수 없으면 NULL — 이때 IP 축은 꺼진다",
        },
    )

    created_at: Optional[datetime] = created_at_field()
    created_by: Optional[int] = created_by_field()
    updated_at: Optional[datetime] = updated_at_field()
    updated_by: Optional[int] = updated_by_field()
