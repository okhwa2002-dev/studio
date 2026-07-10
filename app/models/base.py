from datetime import datetime
from typing import Optional

from sqlalchemy import BigInteger, DateTime, func
from sqlmodel import Field, SQLModel


class BaseEntity(SQLModel):
    id: Optional[int] = Field(
        default=None,
        primary_key=True,
        sa_type=BigInteger,
        sa_column_kwargs={"autoincrement": True, "comment": "기본키, BIGINT 자동 증가"},
    )
    created_at: Optional[datetime] = Field(
        default=None,
        sa_type=DateTime(timezone=False),
        sa_column_kwargs={
            # DB now()는 컨테이너 세션 타임존(UTC) 기준이라 그대로 쓰면 로컬시간
            # 저장 규칙이 깨진다. 항상 Asia/Seoul 벽시계 시각으로 변환해서 저장한다.
            # (APP_TIMEZONE 설정과 달리 DB 표현식이라 런타임 설정을 반영하지 않는다.)
            "nullable": False,
            "server_default": func.timezone("Asia/Seoul", func.now()),
            "comment": "생성일시 (로컬 벽시계 시각, Asia/Seoul 기준, timezone 정보 없음)",
        },
    )
    updated_at: Optional[datetime] = Field(
        default=None,
        sa_type=DateTime(timezone=False),
        sa_column_kwargs={
            "nullable": False,
            "server_default": func.timezone("Asia/Seoul", func.now()),
            "onupdate": func.timezone("Asia/Seoul", func.now()),
            "comment": "수정일시 (로컬 벽시계 시각, 수정 시 갱신)",
        },
    )
    created_by: Optional[int] = Field(
        default=None, sa_type=BigInteger, nullable=True, sa_column_kwargs={"comment": "생성자"}
    )
    updated_by: Optional[int] = Field(
        default=None, sa_type=BigInteger, nullable=True, sa_column_kwargs={"comment": "수정자"}
    )
