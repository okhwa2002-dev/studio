from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import current_user
from app.db import get_db, raw_connection
from app.queries import queries
from app.utils.errors import Errors
from app.utils.time import now_local

router = APIRouter(prefix="/notices", tags=["notices"])


@router.get("")
async def list_notices(
    user: dict = Depends(current_user),
    db: AsyncSession = Depends(get_db),
):
    # 목록에 body까지 실어 보낸다 — 검색이 제목뿐 아니라 본문까지 훑기 때문이다
    # (상세는 GET /notices/{id}가 따로 준다).
    conn = await raw_connection(db)
    rows = queries.list_published_notices(conn, user_id=user["id"], now=now_local())
    return [dict(row) async for row in rows]


@router.get("/popups")
async def list_popup_notices(
    user: dict = Depends(current_user),
    db: AsyncSession = Depends(get_db),
):
    # 읽음 여부를 보지 않는다 — "오늘 하루 보지 않기"는 브라우저가 기억한다.
    conn = await raw_connection(db)
    return [dict(row) async for row in queries.list_popup_notices(conn, now=now_local())]


@router.get("/unread/count")
async def count_unread_notices(
    user: dict = Depends(current_user),
    db: AsyncSession = Depends(get_db),
):
    conn = await raw_connection(db)
    row = await queries.count_unread_notices(conn, user_id=user["id"], now=now_local())
    return {"count": row["n"]}


# 정적 경로(/popups, /unread/count)보다 뒤에 선언한다 — 먼저 두면 "popups"가
# notice_id로 잡힌다.
@router.get("/{notice_id}")
async def get_notice(
    notice_id: int,
    user: dict = Depends(current_user),
    db: AsyncSession = Depends(get_db),
):
    conn = await raw_connection(db)
    row = await queries.find_published_notice_by_id(
        conn, id=notice_id, user_id=user["id"], now=now_local()
    )
    if row is None:
        raise Errors.not_found("공지사항을 찾을 수 없습니다.")
    return dict(row)


@router.post("/{notice_id}/read")
async def mark_notice_read(
    notice_id: int,
    user: dict = Depends(current_user),
    db: AsyncSession = Depends(get_db),
):
    conn = await raw_connection(db)
    now = now_local()
    if (
        await queries.find_published_notice_by_id(
            conn, id=notice_id, user_id=user["id"], now=now
        )
        is None
    ):
        raise Errors.not_found("공지사항을 찾을 수 없습니다.")

    await queries.mark_notice_read(conn, notice_id=notice_id, user_id=user["id"], now=now)
    await db.commit()
    return {"id": notice_id}
