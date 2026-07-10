from datetime import datetime
from typing import Optional

from sqlalchemy import BigInteger, DateTime, func
from sqlmodel import Field, SQLModel


class BaseEntity(SQLModel):
    """모든 테이블의 PK(id)만 제공하는 공통 믹스인.

    생성/수정 감사 컬럼(created_at/created_by/updated_at/updated_by)은 일부러 여기서
    상속시키지 않는다. 믹스인으로 상속하면 Python/SQLAlchemy 규칙상 상속받은 컬럼이
    항상 서브클래스가 선언한 업무 컬럼보다 앞에 오게 되어, "id, 업무 컬럼, 생성/수정
    컬럼" 순서(테이블 생성 규칙)를 만들 수 없다. 대신 아래 *_field() 헬퍼로 설정
    로직만 한 곳에서 관리하고, 각 테이블 클래스가 자기 본문 맨 아래에서 명시적으로
    호출해 선언한다.
    """

    id: Optional[int] = Field(
        default=None,
        primary_key=True,
        sa_type=BigInteger,
        sa_column_kwargs={"autoincrement": True, "comment": "기본키, BIGINT 자동 증가"},
    )


def created_at_field():
    return Field(
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


def created_by_field(foreign_key: Optional[str] = None, comment: str = "생성자"):
    kwargs = {
        "default": None,
        "sa_type": BigInteger,
        "nullable": True,
        "sa_column_kwargs": {"comment": comment},
    }
    if foreign_key:
        kwargs["foreign_key"] = foreign_key
    return Field(**kwargs)


def updated_at_field():
    return Field(
        default=None,
        sa_type=DateTime(timezone=False),
        sa_column_kwargs={
            "nullable": False,
            "server_default": func.timezone("Asia/Seoul", func.now()),
            "onupdate": func.timezone("Asia/Seoul", func.now()),
            "comment": "수정일시 (로컬 벽시계 시각, 수정 시 갱신)",
        },
    )


def updated_by_field(foreign_key: Optional[str] = None, comment: str = "수정자"):
    kwargs = {
        "default": None,
        "sa_type": BigInteger,
        "nullable": True,
        "sa_column_kwargs": {"comment": comment},
    }
    if foreign_key:
        kwargs["foreign_key"] = foreign_key
    return Field(**kwargs)
