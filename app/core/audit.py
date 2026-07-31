from typing import Optional

from fastapi import Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.constants import YN, AuditAction, AuditTarget
from app.db import raw_connection
from app.queries import queries
from app.utils.time import now_local

# 컬럼 길이와 같은 값. 넘치는 값은 여기서 자른다 — 감사 INSERT가 실패할 수 있는
# 현실적인 원인은 값 길이뿐이고, 그것을 없애야 try/except로 삼키지 않을 수 있다.
_EMAIL_MAX = 255
_NAME_MAX = 50
_LABEL_MAX = 200
_PATH_MAX = 255
_SUMMARY_MAX = 200


def _clip(value: Optional[str], limit: int) -> Optional[str]:
    return value[:limit] if value is not None else None


async def record(
    conn,
    *,
    action: AuditAction,
    request: Optional[Request] = None,
    actor: Optional[dict] = None,
    actor_email: Optional[str] = None,
    target_type: Optional[AuditTarget] = None,
    target_id: Optional[int] = None,
    target_label: Optional[str] = None,
    success: bool = True,
    summary: Optional[str] = None,
) -> None:
    """현재 트랜잭션에 감사 행을 넣는다. 원 작업과 함께 커밋되고 함께 롤백된다.

    이것이 기본형이다 — 일어나지 않은 일(롤백된 작업)은 기록되지 않아야 한다.
    예외를 던지며 끝나는 경로에서는 record_failure를 쓴다(그쪽 독스트링 참고).

    actor에는 current_user/require_admin이 준 dict를 그대로 넘긴다. asyncpg Record도
    ["key"] 접근이 되므로 find_by_email/find_by_id의 결과를 그대로 넘겨도 된다.
    actor_email을 따로 받는 경우는 하나뿐이다 — 계정이 없어 dict가 없고 입력한
    이메일 문자열만 있는 로그인 실패.

    IP는 request.client.host만 쓴다. X-Forwarded-For를 읽지 않는 이유: 이 앱은
    FastAPI가 dist를 직접 서빙하는 단독 배포라 프록시가 없고, 프록시가 없는데 그
    헤더를 신뢰하면 누구나 헤더 한 줄로 감사 로그의 IP를 위조할 수 있다.
    """
    await queries.insert_audit_log(
        conn,
        action=action,
        actor_id=actor["id"] if actor is not None else None,
        actor_email=_clip(
            actor["email"] if actor is not None else actor_email, _EMAIL_MAX
        ),
        actor_name=_clip(actor["name"] if actor is not None else None, _NAME_MAX),
        actor_ip=request.client.host if request is not None and request.client else None,
        target_type=target_type,
        target_id=target_id,
        target_label=_clip(target_label, _LABEL_MAX),
        http_method=request.method if request is not None else None,
        http_path=_clip(request.url.path if request is not None else None, _PATH_MAX),
        success_yn=YN.Y if success else YN.N,
        summary=_clip(summary, _SUMMARY_MAX),
        created_at=now_local(),
    )


async def record_failure(db: AsyncSession, **kwargs) -> None:
    """감사 행을 넣고 즉시 커밋한다. 예외를 던지며 끝나는 경로 전용.

    get_db는 세션을 닫기만 하고 커밋하지 않는다(app/db.py). 그래서 401/403/423으로
    끝나는 경로에서 record만 부르면 감사 행이 조용히 사라진다 — 하필 기록이 가장
    중요한 실패 사건에서만. 함수를 나눠 그 위험에 이름을 붙였다.

    주의: 아직 커밋되지 않은 다른 변경이 있으면 그것도 함께 커밋된다. 새 호출부를
    추가할 때 그 지점까지 조회만 했는지 확인할 것.
    """
    conn = await raw_connection(db)
    await record(conn, **kwargs)
    await db.commit()
