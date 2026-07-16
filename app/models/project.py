from datetime import datetime
from typing import Optional

from sqlalchemy import BigInteger
from sqlalchemy.dialects.postgresql import JSONB
from sqlmodel import Field

from app.constants import ProjectStatus, StageName
from app.models.base import (
    BaseEntity,
    created_at_field,
    created_by_field,
    updated_at_field,
    updated_by_field,
)


class Project(BaseEntity, table=True):
    __tablename__ = "projects"
    __table_args__ = {"comment": "쇼츠 생성 프로젝트"}

    owner_id: int = Field(
        sa_type=BigInteger,
        foreign_key="users.id",
        index=True,
        sa_column_kwargs={"comment": "소유자 (FK: users.id, 데이터 격리)"},
    )
    title: str = Field(sa_column_kwargs={"comment": "프로젝트 제목"})
    topic: str = Field(sa_column_kwargs={"comment": "주제/프롬프트"})
    status: str = Field(
        default=ProjectStatus.DRAFT,
        sa_column_kwargs={"comment": "상태: DRAFT | REVIEW | DONE"},
    )
    current_stage: str = Field(
        default=StageName.SCRIPT,
        sa_column_kwargs={"comment": "현재 단계 이름 (예: script)"},
    )
    settings: dict = Field(
        default_factory=dict,
        sa_type=JSONB,
        sa_column_kwargs={"nullable": False, "comment": "스타일·provider 선택 등 (JSONB)"},
    )

    created_at: Optional[datetime] = created_at_field()
    created_by: Optional[int] = created_by_field(foreign_key="users.id")
    updated_at: Optional[datetime] = updated_at_field()
    updated_by: Optional[int] = updated_by_field(foreign_key="users.id")
