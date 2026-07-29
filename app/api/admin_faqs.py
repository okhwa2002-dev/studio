from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field, field_validator
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import require_admin
from app.constants import FaqCategory, FaqStatus
from app.db import get_db, raw_connection
from app.queries import queries
from app.utils.errors import Errors
from app.utils.time import now_local

router = APIRouter(prefix="/admin/faqs", tags=["admin"])


class FaqRequest(BaseModel):
    """FAQ 생성·수정 요청.

    수정도 편집 가능한 필드를 전부 받는다(관리자 모달이 항상 전체를 보낸다).
    category·status를 열거형으로 선언해 코드값 외의 값은 FastAPI가 422로 거른다.
    """

    question: str
    answer: str
    category: FaqCategory
    status: FaqStatus = FaqStatus.DRAFT
    # 음수를 허용하면 "맨 위로 올리기"를 0으로도 음수로도 할 수 있게 되어
    # 같은 목적의 값이 두 갈래가 된다.
    sort_order: int = Field(default=0, ge=0)

    @field_validator("question", "answer")
    @classmethod
    def _not_blank(cls, v: str) -> str:
        # 앞뒤 공백을 다듬고, 공백뿐인 값은 거부한다(→ FastAPI가 422로 응답).
        v = v.strip()
        if not v:
            raise ValueError("빈 값일 수 없습니다.")
        return v


@router.get("")
async def list_faqs(
    db: AsyncSession = Depends(get_db),
    admin: dict = Depends(require_admin),
):
    # 상태 필터·검색은 프론트가 클라이언트에서 처리한다(admin_notices와 같은 방침).
    conn = await raw_connection(db)
    return [dict(row) async for row in queries.list_faqs_for_admin(conn)]


@router.post("", status_code=201)
async def create_faq(
    body: FaqRequest,
    db: AsyncSession = Depends(get_db),
    admin: dict = Depends(require_admin),
):
    conn = await raw_connection(db)
    now = now_local()
    faq_id = await queries.insert_faq(
        conn,
        question=body.question,
        answer=body.answer,
        category=body.category,
        status=body.status,
        sort_order=body.sort_order,
        created_at=now,
        updated_at=now,
        created_by=admin["id"],
        updated_by=admin["id"],
    )
    await db.commit()
    return {"id": faq_id}


async def _load_faq(conn, faq_id: int) -> dict:
    row = await queries.find_faq_by_id(conn, id=faq_id)
    if row is None:
        # 이미 소프트 삭제된 FAQ도 여기서 걸린다(쿼리가 deleted_at IS NULL로 거른다).
        raise Errors.not_found("FAQ를 찾을 수 없습니다.")
    return dict(row)


@router.patch("/{faq_id}")
async def update_faq(
    faq_id: int,
    body: FaqRequest,
    db: AsyncSession = Depends(get_db),
    admin: dict = Depends(require_admin),
):
    conn = await raw_connection(db)
    await _load_faq(conn, faq_id)

    await queries.update_faq(
        conn,
        id=faq_id,
        question=body.question,
        answer=body.answer,
        category=body.category,
        status=body.status,
        sort_order=body.sort_order,
        updated_at=now_local(),
        updated_by=admin["id"],
    )
    await db.commit()
    return {"id": faq_id}


@router.delete("/{faq_id}")
async def delete_faq(
    faq_id: int,
    db: AsyncSession = Depends(get_db),
    admin: dict = Depends(require_admin),
):
    conn = await raw_connection(db)
    await _load_faq(conn, faq_id)

    now = now_local()
    await queries.soft_delete_faq(conn, id=faq_id, deleted_at=now, deleted_by=admin["id"])
    await db.commit()
    return {"id": faq_id, "deleted_at": now}
