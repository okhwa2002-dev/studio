from datetime import datetime
from typing import Optional

from sqlmodel import Field

from app.models.base import BaseEntity


class RefreshToken(BaseEntity, table=True):
    __tablename__ = "refresh_tokens"
    __table_args__ = {"comment": "리프레시 토큰 (회전/폐기 관리)"}

    user_id: int = Field(
        foreign_key="users.id",
        index=True,
        sa_column_kwargs={"comment": "리프레시 토큰 소유자 (FK: users.id)"},
    )
    token_hash: str = Field(
        unique=True,
        index=True,
        sa_column_kwargs={"comment": "리프레시 토큰의 SHA-256 해시값 (원문 저장 안 함)"},
    )
    expires_at: datetime = Field(sa_column_kwargs={"comment": "만료 일시"})
    revoked_at: Optional[datetime] = Field(
        default=None,
        sa_column_kwargs={"comment": "폐기(회전/로그아웃) 처리 일시, 미폐기 시 NULL"},
    )
