from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import current_user
from app.db import get_db, raw_connection
from app.queries import queries

router = APIRouter(prefix="/faqs", tags=["faqs"])


@router.get("")
async def list_faqs(
    user: dict = Depends(current_user),
    db: AsyncSession = Depends(get_db),
):
    # 목록에 answer까지 실어 보낸다 — 아코디언은 이미 받은 답변을 펼치는 구조라,
    # 상세 조회 API를 두면 질문을 누를 때마다 왕복이 생기고 펼치는 동안 빈 영역이 보인다.
    conn = await raw_connection(db)
    return [dict(row) async for row in queries.list_published_faqs(conn)]
