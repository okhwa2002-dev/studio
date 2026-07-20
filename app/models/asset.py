from datetime import datetime
from typing import Optional

from sqlalchemy import BigInteger
from sqlalchemy.dialects.postgresql import JSONB
from sqlmodel import Field

from app.models.base import (
    BaseEntity,
    created_at_field,
    created_by_field,
    updated_at_field,
    updated_by_field,
)


class Asset(BaseEntity, table=True):
    __tablename__ = "assets"
    __table_args__ = {"comment": "단계 산출물 파일 (음성·자막·영상)"}

    stage_id: int = Field(
        sa_type=BigInteger,
        foreign_key="stages.id",
        index=True,
        sa_column_kwargs={"comment": "소속 단계 (FK: stages.id)"},
    )
    kind: str = Field(sa_column_kwargs={"comment": "산출물 종류: AUDIO (이후 SRT|VIDEO|IMAGE)"})
    path: str = Field(sa_column_kwargs={"comment": "STORAGE_PATH 기준 상대 경로"})
    meta: dict = Field(
        default_factory=dict,
        sa_type=JSONB,
        sa_column_kwargs={"nullable": False, "comment": "voice·size_bytes 등 부가정보 (JSONB)"},
    )

    created_at: Optional[datetime] = created_at_field()
    created_by: Optional[int] = created_by_field(foreign_key="users.id")
    updated_at: Optional[datetime] = updated_at_field()
    updated_by: Optional[int] = updated_by_field(foreign_key="users.id")
