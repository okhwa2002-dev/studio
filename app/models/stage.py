from datetime import datetime
from typing import Optional

from sqlalchemy import BigInteger
from sqlalchemy.dialects.postgresql import JSONB
from sqlmodel import Field

from app.constants import StageStatus
from app.models.base import (
    BaseEntity,
    created_at_field,
    created_by_field,
    updated_at_field,
    updated_by_field,
)


class Stage(BaseEntity, table=True):
    __tablename__ = "stages"
    __table_args__ = {"comment": "파이프라인 단계 (script|voice|captions|render)"}

    project_id: int = Field(
        sa_type=BigInteger,
        foreign_key="projects.id",
        index=True,
        sa_column_kwargs={"comment": "소속 프로젝트 (FK: projects.id)"},
    )
    name: str = Field(sa_column_kwargs={"comment": "단계 이름 (예: script)"})
    provider: str = Field(sa_column_kwargs={"comment": "사용한 provider 이름 (예: fake)"})
    status: str = Field(
        default=StageStatus.PENDING,
        sa_column_kwargs={"comment": "상태: PENDING|QUEUED|RUNNING|NEEDS_REVIEW|APPROVED|FAILED"},
    )
    output: dict = Field(
        default_factory=dict,
        sa_type=JSONB,
        sa_column_kwargs={"nullable": False, "comment": "산출물 (script는 대본 JSON, JSONB)"},
    )
    error: Optional[str] = Field(
        default=None, sa_column_kwargs={"comment": "실패 메시지 (성공/미실행 시 NULL)"}
    )
    attempt: int = Field(
        default=0,
        sa_column_kwargs={"server_default": "0", "comment": "재생성 횟수 (재생성 시 +1)"},
    )
    started_at: Optional[datetime] = Field(
        default=None, sa_column_kwargs={"comment": "실행 시작 일시"}
    )
    finished_at: Optional[datetime] = Field(
        default=None, sa_column_kwargs={"comment": "실행 종료(성공/실패) 일시"}
    )

    created_at: Optional[datetime] = created_at_field()
    created_by: Optional[int] = created_by_field(foreign_key="users.id")
    updated_at: Optional[datetime] = updated_at_field()
    updated_by: Optional[int] = updated_by_field(foreign_key="users.id")
