from datetime import datetime

from fastapi import APIRouter, Depends
from pydantic import BaseModel, field_validator
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import require_admin
from app.constants import YN, NoticeStatus
from app.db import get_db, raw_connection
from app.queries import queries
from app.utils.errors import Errors
from app.utils.time import now_local

router = APIRouter(prefix="/admin/notices", tags=["admin"])


class NoticeRequest(BaseModel):
    """공지 생성·수정 요청.

    수정도 편집 가능한 필드를 전부 받는다(관리자 모달이 항상 전체를 보낸다).
    pinned_yn·popup_yn을 YN으로 선언해 'Y'/'N' 외의 값은 FastAPI가 422로 거른다.
    """

    title: str
    body: str
    status: NoticeStatus = NoticeStatus.DRAFT
    pinned_yn: YN = YN.N
    popup_yn: YN = YN.N
    starts_at: datetime | None = None
    ends_at: datetime | None = None

    @field_validator("title", "body")
    @classmethod
    def _not_blank(cls, v: str) -> str:
        # 앞뒤 공백을 다듬고, 공백뿐인 값은 거부한다(→ FastAPI가 422로 응답).
        v = v.strip()
        if not v:
            raise ValueError("빈 값일 수 없습니다.")
        return v


def _resolve_period(body: NoticeRequest) -> tuple[datetime | None, datetime | None]:
    """게시 상태에 따라 starts_at을 확정하고 기간이 뒤집혔는지 검사한다.

    임시저장은 "아직 게시된 적 없음"이므로 게시일을 비운다. 게시로 올릴 때
    시작 일시를 주지 않았으면 그 순간이 게시일이 되고, 미래 값을 주면 예약 게시다.
    """
    if body.status == NoticeStatus.DRAFT:
        return None, body.ends_at

    starts_at = body.starts_at or now_local()
    if body.ends_at is not None and body.ends_at <= starts_at:
        raise Errors.bad_request("종료 일시는 시작 일시보다 뒤여야 합니다.")
    return starts_at, body.ends_at


@router.get("")
async def list_notices(
    db: AsyncSession = Depends(get_db),
    admin: dict = Depends(require_admin),
):
    # 상태 필터·검색은 프론트가 클라이언트에서 처리한다(admin_projects와 같은 방침).
    conn = await raw_connection(db)
    return [dict(row) async for row in queries.list_notices_for_admin(conn)]


@router.post("", status_code=201)
async def create_notice(
    body: NoticeRequest,
    db: AsyncSession = Depends(get_db),
    admin: dict = Depends(require_admin),
):
    starts_at, ends_at = _resolve_period(body)

    conn = await raw_connection(db)
    now = now_local()
    notice_id = await queries.insert_notice(
        conn,
        title=body.title,
        body=body.body,
        status=body.status,
        pinned_yn=body.pinned_yn,
        popup_yn=body.popup_yn,
        starts_at=starts_at,
        ends_at=ends_at,
        created_at=now,
        updated_at=now,
        created_by=admin["id"],
        updated_by=admin["id"],
    )
    await db.commit()
    return {"id": notice_id}


async def _load_notice(conn, notice_id: int) -> dict:
    row = await queries.find_notice_by_id(conn, id=notice_id)
    if row is None:
        # 이미 소프트 삭제된 공지도 여기서 걸린다(쿼리가 deleted_at IS NULL로 거른다).
        raise Errors.not_found("공지사항을 찾을 수 없습니다.")
    return dict(row)


@router.patch("/{notice_id}")
async def update_notice(
    notice_id: int,
    body: NoticeRequest,
    db: AsyncSession = Depends(get_db),
    admin: dict = Depends(require_admin),
):
    conn = await raw_connection(db)
    await _load_notice(conn, notice_id)

    starts_at, ends_at = _resolve_period(body)
    now = now_local()
    await queries.update_notice(
        conn,
        id=notice_id,
        title=body.title,
        body=body.body,
        status=body.status,
        pinned_yn=body.pinned_yn,
        popup_yn=body.popup_yn,
        starts_at=starts_at,
        ends_at=ends_at,
        updated_at=now,
        updated_by=admin["id"],
    )
    await db.commit()
    return {"id": notice_id}


@router.delete("/{notice_id}")
async def delete_notice(
    notice_id: int,
    db: AsyncSession = Depends(get_db),
    admin: dict = Depends(require_admin),
):
    conn = await raw_connection(db)
    await _load_notice(conn, notice_id)

    now = now_local()
    await queries.soft_delete_notice(
        conn, id=notice_id, deleted_at=now, deleted_by=admin["id"]
    )
    await db.commit()
    return {"id": notice_id, "deleted_at": now}
