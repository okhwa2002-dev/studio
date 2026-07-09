from datetime import datetime
from typing import Optional

from sqlalchemy import BigInteger, DateTime
from sqlmodel import Field, SQLModel

from app.utils.time import now_local


class BaseEntity(SQLModel):
    id: Optional[int] = Field(
        default=None,
        primary_key=True,
        sa_type=BigInteger,
        sa_column_kwargs={"autoincrement": True},
    )
    created_at: Optional[datetime] = Field(
        default_factory=now_local,
        sa_type=DateTime(timezone=False),
        sa_column_kwargs={"nullable": False},
    )
    updated_at: Optional[datetime] = Field(
        default_factory=now_local,
        sa_type=DateTime(timezone=False),
        sa_column_kwargs={"nullable": False, "onupdate": now_local},
    )
    created_by: Optional[int] = Field(default=None, sa_type=BigInteger, nullable=True)
    updated_by: Optional[int] = Field(default=None, sa_type=BigInteger, nullable=True)
