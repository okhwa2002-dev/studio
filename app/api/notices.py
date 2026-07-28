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
    # 목록에 body까지 실어 보낸다 — 공지는 건수가 적고, 상세 모달이 이미 받은
    # 행을 그대로 쓰므로 별도 상세 조회 API가 필요 없다.
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


@router.post("/{notice_id}/read")
async def mark_notice_read(
    notice_id: int,
    user: dict = Depends(current_user),
    db: AsyncSession = Depends(get_db),
):
    conn = await raw_connection(db)
    now = now_local()
    if await queries.find_visible_notice_by_id(conn, id=notice_id, now=now) is None:
        raise Errors.not_found("공지사항을 찾을 수 없습니다.")

    await queries.mark_notice_read(conn, notice_id=notice_id, user_id=user["id"], now=now)
    await db.commit()
    return {"id": notice_id}
