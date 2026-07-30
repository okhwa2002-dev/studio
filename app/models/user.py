from datetime import datetime
from typing import Optional

from sqlalchemy import BigInteger
from sqlmodel import Field

from app.constants import UserRole, UserStatus
from app.models.base import (
    BaseEntity,
    created_at_field,
    created_by_field,
    updated_at_field,
    updated_by_field,
)


class User(BaseEntity, table=True):
    __tablename__ = "users"
    __table_args__ = {"comment": "사용자 계정 (자율 회원가입 + 관리자 승인)"}

    email: str = Field(
        unique=True, index=True, sa_column_kwargs={"comment": "로그인 이메일, UNIQUE"}
    )
    # default=""는 테스트 편의용이다(수많은 테스트가 이름 없이 User(...)를 만든다).
    # 프로덕션 쓰기는 raw SQL insert_user만 쓰고 거기서 name을 명시적으로 받으므로,
    # 빈 이름이 이 기본값으로 저장되는 일은 없다. ORM 쓰기 경로를 새로 만들면 이 점을 유의할 것.
    name: str = Field(
        default="",
        sa_column_kwargs={"comment": "표시용 이름 (로그인 식별자는 email)"},
    )
    password_hash: str = Field(
        sa_column_kwargs={"comment": "argon2 해시 값 (평문 저장 금지)"}
    )
    role: str = Field(
        default=UserRole.MEMBER,
        sa_column_kwargs={"comment": "권한: MEMBER | ADMIN (기본값 MEMBER)"},
    )
    status: str = Field(
        default=UserStatus.PENDING,
        sa_column_kwargs={
            "comment": "가입 상태: PENDING | ACTIVE | DISABLED | REJECTED (기본값 PENDING)"
        },
    )
    approved_at: Optional[datetime] = Field(
        default=None, sa_column_kwargs={"comment": "관리자가 승인/거절 처리한 일시"}
    )
    approved_by: Optional[int] = Field(
        default=None,
        sa_type=BigInteger,
        foreign_key="users.id",
        nullable=True,
        sa_column_kwargs={"comment": "승인/거절한 관리자 (FK: users.id 자기참조)"},
    )
    failed_login_count: int = Field(
        default=0,
        sa_column_kwargs={
            "server_default": "0",
            "comment": "연속 로그인 실패 횟수 (성공 시 0으로 리셋)",
        },
    )
    locked_at: Optional[datetime] = Field(
        default=None,
        sa_column_kwargs={"comment": "계정 잠긴 시각 (NULL=안 잠김, 값 있음=잠김)"},
    )
    unlocked_at: Optional[datetime] = Field(
        default=None,
        sa_column_kwargs={"comment": "관리자가 잠금 해제한 시각 (해제일시)"},
    )
    # server_default를 두는 이유는 failed_login_count와 같다 — raw SQL insert_user가
    # 이 컬럼을 넘기지 않으므로 DB가 기본값을 채워야 한다.
    must_change_password: bool = Field(
        default=False,
        sa_column_kwargs={
            "server_default": "false",
            "comment": "관리자 초기화 후 비밀번호 변경 강제 여부 (true=변경 전까지 다른 API 차단)",
        },
    )

    created_at: Optional[datetime] = created_at_field()
    created_by: Optional[int] = created_by_field(
        foreign_key="users.id", comment="생성자 (FK: users.id 자기참조) — 자율가입은 NULL"
    )
    updated_at: Optional[datetime] = updated_at_field()
    updated_by: Optional[int] = updated_by_field(
        foreign_key="users.id", comment="수정자 (FK: users.id 자기참조)"
    )
