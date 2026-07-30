from datetime import datetime
from typing import Optional

from sqlalchemy import CHAR, BigInteger, Index
from sqlmodel import Field

from app.constants import YN
from app.models.base import BaseEntity, created_at_field


class AuditLog(BaseEntity, table=True):
    """활동 기록. 한 번 쓰면 고치지 않는다(append-only).

    updated_at/updated_by를 두지 않는 이유가 그것이다 — UPDATE 경로를 아예 만들지
    않는 것이 "기록은 고쳐지지 않는다"를 지키는 가장 단순한 방법이다.

    actor_email/actor_name/target_label은 JOIN으로 뽑을 수 있는데도 행에 복사해 둔다.
    감사 로그는 "지금 그 대상이 어떤 상태인가"가 아니라 "그때 무슨 일이 있었나"의
    기록이다. 특히 프로젝트는 30일 뒤 정리 잡이 행을 완전히 지우므로(cleanup.py),
    JOIN 방식이면 삭제 기록만 남고 무엇을 삭제했는지가 사라진다.
    """

    __tablename__ = "audit_logs"
    __table_args__ = (
        # ORDER BY created_at DESC, id DESC 를 위한 인덱스. DESC로 만들지 않는 이유:
        # Postgres는 오름차순 인덱스를 역방향으로 스캔할 수 있어 결과가 같고,
        # 표현식/정렬옵션 없는 평범한 인덱스가 마이그레이션에서도 단순하다.
        Index("ix_audit_logs_created_at_id", "created_at", "id"),
        Index("ix_audit_logs_actor_id", "actor_id"),
        Index("ix_audit_logs_action", "action"),
        {"comment": "활동 기록 (감사 로그, append-only)"},
    )

    action: str = Field(sa_column_kwargs={"comment": "행위 코드 (AuditAction)"})
    # NULL 가능: 존재하지 않는 이메일로 로그인을 시도하면 특정할 계정이 없다.
    actor_id: Optional[int] = Field(
        default=None,
        sa_type=BigInteger,
        foreign_key="users.id",
        nullable=True,
        sa_column_kwargs={"comment": "행위자 (FK: users.id, 계정 미상이면 NULL)"},
    )
    actor_email: Optional[str] = Field(
        default=None, max_length=255,
        sa_column_kwargs={"comment": "행위 시점 이메일 스냅샷 (로그인 실패는 입력값 그대로)"},
    )
    actor_name: Optional[str] = Field(
        default=None, max_length=50, sa_column_kwargs={"comment": "행위 시점 이름 스냅샷"}
    )
    actor_ip: Optional[str] = Field(
        default=None, max_length=45, sa_column_kwargs={"comment": "요청 IP (IPv6까지)"}
    )
    # target_id에 FK를 걸지 않는다 — FK가 있으면 대상 행을 지울 때 감사 기록이
    # 걸림돌이 되고, ON DELETE SET NULL을 붙이면 과거 기록이 소급해서 비어버린다.
    target_type: Optional[str] = Field(
        default=None, sa_column_kwargs={"comment": "대상 종류 (AuditTarget)"}
    )
    target_id: Optional[int] = Field(
        default=None, sa_type=BigInteger, nullable=True,
        sa_column_kwargs={"comment": "대상 행 id (FK 아님)"},
    )
    target_label: Optional[str] = Field(
        default=None, max_length=200,
        sa_column_kwargs={"comment": "대상 이름 스냅샷 (프로젝트 제목·사용자 이름 등)"},
    )
    http_method: Optional[str] = Field(
        default=None, max_length=10, sa_column_kwargs={"comment": "호출한 HTTP 메서드"}
    )
    http_path: Optional[str] = Field(
        default=None, max_length=255,
        sa_column_kwargs={"comment": "호출한 실제 경로 (템플릿 아님)"},
    )
    success_yn: str = Field(
        default=YN.Y,
        sa_type=CHAR(1),
        sa_column_kwargs={"server_default": "Y", "comment": "성공 여부: Y | N"},
    )
    summary: Optional[str] = Field(
        default=None, max_length=200, sa_column_kwargs={"comment": "한 줄 설명"}
    )

    created_at: Optional[datetime] = created_at_field()
