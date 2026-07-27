from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import require_admin
from app.db import get_db, raw_connection
from app.queries import queries

router = APIRouter(prefix="/admin/projects", tags=["admin"])


@router.get("")
async def list_all_projects(
    db: AsyncSession = Depends(get_db),
    admin: dict = Depends(require_admin),
):
    # 소유자 무관 전체 프로젝트. 상태 필터·검색은 프론트가 클라이언트에서 처리한다.
    conn = await raw_connection(db)
    return [dict(row) async for row in queries.list_all_projects(conn)]
