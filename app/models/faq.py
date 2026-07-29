from datetime import datetime
from typing import Optional

from sqlalchemy import BigInteger, Text
from sqlmodel import Field

from app.constants import FaqStatus
from app.models.base import (
    BaseEntity,
    created_at_field,
    created_by_field,
    updated_at_field,
    updated_by_field,
)


class Faq(BaseEntity, table=True):
    __tablename__ = "faqs"
    __table_args__ = {"comment": "자주 묻는 질문 (관리자 작성, 전체 사용자 열람)"}

    question: str = Field(sa_column_kwargs={"comment": "질문"})
    answer: str = Field(
        sa_type=Text,
        sa_column_kwargs={"comment": "답변 (일반 텍스트, 줄바꿈 그대로 표시)"},
    )
    # 기본값을 두지 않는다 — 분류는 관리자가 반드시 고르는 값이라, 빠뜨렸을 때
    # 조용히 '기타'로 들어가는 것보다 요청 단계에서 걸리는 편이 낫다.
    category: str = Field(
        sa_column_kwargs={"comment": "분류: ACCOUNT | PROJECT | PRODUCTION | ETC"}
    )
    status: str = Field(
        default=FaqStatus.DRAFT,
        sa_column_kwargs={"comment": "상태: DRAFT | PUBLISHED (기본값 DRAFT)"},
    )
    # 공지의 pinned_yn 자리를 대신한다. FAQ에서 중요한 건 "맨 위 한 건"이 아니라
    # 전체 순서라, 순서를 정하는 수단을 이 컬럼 하나로 둔다.
    sort_order: int = Field(
        default=0,
        sa_column_kwargs={"server_default": "0", "comment": "목록 정렬 순서 (작을수록 위)"},
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
