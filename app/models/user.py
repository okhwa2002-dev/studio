from datetime import datetime
from typing import Optional

from sqlalchemy import BigInteger
from sqlmodel import Field

from app.models.base import BaseEntity


class User(BaseEntity, table=True):
    __tablename__ = "users"

    email: str = Field(unique=True, index=True)
    password_hash: str
    role: str = Field(default="member")
    status: str = Field(default="pending")
    approved_at: Optional[datetime] = Field(default=None)
    approved_by: Optional[int] = Field(
        default=None, sa_type=BigInteger, foreign_key="users.id", nullable=True
    )
    created_by: Optional[int] = Field(
        default=None, sa_type=BigInteger, foreign_key="users.id", nullable=True
    )
    updated_by: Optional[int] = Field(
        default=None, sa_type=BigInteger, foreign_key="users.id", nullable=True
    )
