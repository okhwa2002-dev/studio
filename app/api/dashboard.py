from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import current_user
from app.constants import UserRole
from app.db import get_db, raw_connection
from app.queries import queries

router = APIRouter(prefix="/dashboard", tags=["dashboard"])

_ATTENTION_LIMIT = 5


async def _project_counts(rows) -> dict:
    # 상태별 행({status, n})을 {total, draft, review, done} 형태로 접는다.
    counts = {"total": 0, "draft": 0, "review": 0, "done": 0}
    async for row in rows:
        counts[row["status"].lower()] = row["n"]
        counts["total"] += row["n"]
    return counts


@router.get("/summary")
async def summary(user: dict = Depends(current_user), db: AsyncSession = Depends(get_db)):
    conn = await raw_connection(db)

    projects = await _project_counts(
        queries.count_projects_by_status_for_owner(conn, owner_id=user["id"])
    )
    attention = [
        {
            "id": r["id"],
            "title": r["title"],
            "current_stage": r["current_stage"],
            "needs_review": r["needs_review"],
            "failed": r["failed"],
        }
        async for r in queries.list_owner_attention_projects(
            conn, owner_id=user["id"], limit=_ATTENTION_LIMIT
        )
    ]

    # 관리자에게만 운영 지표를 덧붙인다. 멤버 응답에서는 admin이 null이다.
    admin = None
    if user["role"] == UserRole.ADMIN:
        u = dict(await queries.count_users_summary(conn))
        s = dict(await queries.count_stages_health(conn))
        admin = {
            "users": {"active": u["active"], "pending": u["pending"], "locked": u["locked"]},
            "projects": await _project_counts(queries.count_projects_by_status(conn)),
            "stages": {
                "running": s["running"],
                "failed": s["failed"],
                "needs_review": s["needs_review"],
            },
        }

    return {"projects": projects, "attention": attention, "admin": admin}
