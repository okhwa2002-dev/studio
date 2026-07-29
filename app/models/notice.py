from datetime import datetime
from typing import Optional

from sqlalchemy import CHAR, BigInteger, Text
from sqlmodel import Field

from app.constants import YN, NoticeStatus
from app.models.base import (
    BaseEntity,
    created_at_field,
    created_by_field,
    updated_at_field,
    updated_by_field,
)


class Notice(BaseEntity, table=True):
    __tablename__ = "notices"
    __table_args__ = {"comment": "공지사항 (관리자 작성, 전체 사용자 열람)"}

    title: str = Field(sa_column_kwargs={"comment": "공지 제목"})
    body: str = Field(
        sa_type=Text,
        sa_column_kwargs={"comment": "본문 (일반 텍스트, 줄바꿈 그대로 표시)"},
    )
    status: str = Field(
        default=NoticeStatus.DRAFT,
        sa_column_kwargs={"comment": "상태: DRAFT | PUBLISHED (기본값 DRAFT)"},
    )
    pinned_yn: str = Field(
        default=YN.N,
        sa_type=CHAR(1),
        sa_column_kwargs={"server_default": "N", "comment": "목록 상단 고정 여부: Y | N"},
    )
    popup_yn: str = Field(
        default=YN.N,
        sa_type=CHAR(1),
        sa_column_kwargs={"server_default": "N", "comment": "메인 팝업 노출 여부: Y | N"},
    )
    # 게시일은 이 컬럼 하나다. 게시로 올릴 때 비어 있으면 서버가 그 시각으로 채우고,
    # 미래 값을 넣으면 예약 게시가 된다. 임시저장으로 되돌리면 다시 NULL이 된다.
    starts_at: Optional[datetime] = Field(
        default=None, sa_column_kwargs={"comment": "게시 시작 일시 (DRAFT면 NULL)"}
    )
    ends_at: Optional[datetime] = Field(
        default=None, sa_column_kwargs={"comment": "게시 종료 일시 (NULL=무기한)"}
    )
    deleted_at: Optional[datetime] = Field(
        default=None, sa_column_kwargs={"comment": "소프트 삭제 일시 (NULL=미삭제)"}
    )
    deleted_by: Optional[int] = Field(
        default=None,
        sa_type=BigInteger,
        foreign_key="users.id",
        nullable=True,
        sa_column_kwargs={"comment": "삭제한 관리자 (FK: users.id)"},
    )

    created_at: Optional[datetime] = created_at_field()
    created_by: Optional[int] = created_by_field(foreign_key="users.id")
    updated_at: Optional[datetime] = updated_at_field()
    updated_by: Optional[int] = updated_by_field(foreign_key="users.id")
