from datetime import datetime
from typing import Optional

from sqlalchemy import Text
from sqlmodel import Field

from app.models.base import (
    BaseEntity,
    created_at_field,
    created_by_field,
    updated_at_field,
    updated_by_field,
)


class SystemSetting(BaseEntity, table=True):
    __tablename__ = "system_settings"
    __table_args__ = {"comment": "시스템 설정 (관리자가 기본값에서 바꾼 항목만 저장)"}

    # RuntimeSettings의 필드명과 1:1로 맞춘다. 모델에 없는 키는 읽을 때 무시된다.
    key: str = Field(
        unique=True,
        sa_column_kwargs={"comment": "설정 키 (RuntimeSettings 필드명)"},
    )
    # 타입은 DB가 아니라 RuntimeSettings가 안다. 값은 JSON 문자열로 통일해
    # bool·int·list·str을 한 규칙으로 다룬다.
    value: str = Field(
        sa_type=Text,
        sa_column_kwargs={"comment": "설정값 (JSON 직렬화 문자열)"},
    )

    created_at: Optional[datetime] = created_at_field()
    created_by: Optional[int] = created_by_field(foreign_key="users.id")
    updated_at: Optional[datetime] = updated_at_field()
    updated_by: Optional[int] = updated_by_field(foreign_key="users.id")
