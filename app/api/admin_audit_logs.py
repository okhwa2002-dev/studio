from datetime import date, datetime, time, timedelta

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import require_admin
from app.constants import YN, AuditAction
from app.db import get_db, raw_connection
from app.queries import queries
from app.utils.errors import AppError
from app.utils.time import now_local

router = APIRouter(prefix="/admin/audit-logs", tags=["admin"])

# 기본 조회 범위. 화면을 열자마자 보관 기간(90일) 전체에 COUNT(*)가 도는 것을 막는다.
_DEFAULT_DAYS = 7
_MAX_SIZE = 200


@router.get("")
async def list_audit_logs(
    # from은 파이썬 예약어라 인자 이름으로 쓸 수 없다. 화면·URL에 노출되는 이름은
    # to와 짝이 맞아야 하므로 alias로 넘긴다.
    from_date: date | None = Query(None, alias="from"),
    to_date: date | None = Query(None, alias="to"),
    action: AuditAction | None = None,
    success: YN | None = None,
    q: str | None = None,
    page: int = Query(1, ge=1),
    # 화면 기본값(50)과 맞춘다 — 감사 로그는 90일치 × 전체 사용자 쓰기라 20건씩은
    # 훑어보기가 되지 않아 이 화면만 50에서 시작하기로 했다. /docs에 뜨는 값이 화면과
    # 어긋나지 않게 여기도 같이 맞춘다.
    size: int = Query(50, ge=1, le=_MAX_SIZE),
    db: AsyncSession = Depends(get_db),
    admin: dict = Depends(require_admin),
):
    """관리자 활동 기록 조회.

    다른 관리자 목록(공지·FAQ)과 달리 서버에서 필터·페이지네이션한다. 그쪽은 수십 건이라
    "전량 내려주고 프론트가 거른다"가 성립하지만, 감사 로그는 90일치 × 모든 사용자
    쓰기라 수만~수십만 행이 된다.
    """
    today = now_local().date()
    start = from_date or today - timedelta(days=_DEFAULT_DAYS)
    end = to_date or today
    if start > end:
        # 빈 목록으로 답하면 "기록이 없다"와 "조건이 잘못됐다"를 구분할 수 없다.
        raise AppError(422, "VALIDATION_ERROR", "종료 날짜는 시작 날짜보다 뒤여야 합니다.")

    filters = {
        # 날짜만 받아 그날 00:00:00 ~ 23:59:59.999999로 넓힌다. 종료일을 그대로 쓰면
        # 그날 00:00:00 한 순간만 포함되어 "오늘"을 골라도 오후 기록이 전부 빠진다.
        "from_at": datetime.combine(start, time.min),
        "to_at": datetime.combine(end, time.max),
        "action": action,
        "success_yn": success,
        "like": f"%{q}%" if q else None,
    }

    conn = await raw_connection(db)
    total = await queries.count_audit_logs(conn, **filters)
    items = [
        dict(row)
        async for row in queries.list_audit_logs(
            conn, **filters, limit=size, offset=(page - 1) * size
        )
    ]
    return {"items": items, "total": total["n"], "page": page, "size": size}
