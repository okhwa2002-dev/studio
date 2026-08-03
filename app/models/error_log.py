from datetime import datetime
from typing import Optional

from sqlmodel import Field

from app.models.base import (
    BaseEntity,
    created_at_field,
    created_by_field,
    updated_at_field,
    updated_by_field,
)


class ErrorLog(BaseEntity, table=True):
    __tablename__ = "error_logs"
    __table_args__ = {"comment": "에러 로그 (지문 단위 집계, 관리자 화면 없음)"}

    fingerprint: str = Field(
        index=True,
        unique=True,
        sa_column_kwargs={
            "comment": "source + 예외 클래스 + 발생 위치. UPSERT 키. 메시지는 넣지 않는다",
        },
    )
    source: str = Field(
        index=True,
        sa_column_kwargs={"comment": "발생 계층 — http·worker·pipeline·cleanup·email"},
    )
    exc_type: str = Field(sa_column_kwargs={"comment": "예외 클래스명"})
    location: str = Field(
        sa_column_kwargs={"comment": "앱 코드 기준 디렉토리/파일:줄. 트레이스백 전문은 저장하지 않는다"},
    )
    message: str = Field(
        sa_column_kwargs={"comment": "마지막 발생의 예외 메시지 (200자로 자름)"},
    )
    context: Optional[str] = Field(
        default=None,
        sa_column_kwargs={"comment": "마지막 발생의 부가 정보. 호출자가 명시적으로 넘긴 값만"},
    )
    count: int = Field(
        default=1,
        sa_column_kwargs={"server_default": "1", "comment": "누적 발생 횟수"},
    )

    created_at: Optional[datetime] = created_at_field()
    created_by: Optional[int] = created_by_field()
    updated_at: Optional[datetime] = updated_at_field()
    updated_by: Optional[int] = updated_by_field()
