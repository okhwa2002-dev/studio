from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import require_admin
from app.constants import UserStatus
from app.db import get_db, raw_connection
from app.queries import queries
from app.utils.errors import Errors
from app.utils.time import now_local

router = APIRouter(prefix="/admin/users", tags=["admin"])


@router.get("")
async def list_users(
    # UserStatus로 선언하면 FastAPI가 값을 검증한다 → 잘못된 값은 422로 거절된다.
    status: UserStatus = Query(UserStatus.PENDING),
    db: AsyncSession = Depends(get_db),
    admin: dict = Depends(require_admin),
):
    conn = await raw_connection(db)
    return [dict(row) async for row in queries.list_by_status(conn, status=status)]


async def _set_status(
    user_id: int, new_status: str, db: AsyncSession, admin: dict
) -> dict:
    conn = await raw_connection(db)
    row = await queries.find_by_id(conn, id=user_id)
    if row is None:
        raise Errors.not_found("사용자를 찾을 수 없습니다.")

    now = now_local()
    await queries.update_status(
        conn,
        id=user_id,
        status=new_status,
        approved_at=now,
        approved_by=admin["id"],
        updated_at=now,
        updated_by=admin["id"],
    )
    await db.commit()
    return {"id": user_id, "status": new_status}


@router.post("/{user_id}/approve")
async def approve_user(
    user_id: int,
    db: AsyncSession = Depends(get_db),
    admin: dict = Depends(require_admin),
):
    return await _set_status(user_id, UserStatus.ACTIVE, db, admin)


@router.post("/{user_id}/reject")
async def reject_user(
    user_id: int,
    db: AsyncSession = Depends(get_db),
    admin: dict = Depends(require_admin),
):
    return await _set_status(user_id, UserStatus.REJECTED, db, admin)
