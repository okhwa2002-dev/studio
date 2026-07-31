import asyncio

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import require_admin
from app.auth.security import INITIAL_PASSWORD, hash_password
from app.constants import AuditAction, AuditTarget, UserStatus
from app.core import audit
from app.db import get_db, raw_connection
from app.queries import queries
from app.utils.errors import Errors
from app.utils.time import now_local

router = APIRouter(prefix="/admin/users", tags=["admin"])


@router.get("")
async def list_users(
    # UserStatus로 선언하면 FastAPI가 값을 검증한다 → 잘못된 값은 422로 거절된다.
    # status를 생략하면(None) 상태 무관 전체 목록을 반환한다.
    status: UserStatus | None = Query(None),
    db: AsyncSession = Depends(get_db),
    admin: dict = Depends(require_admin),
):
    conn = await raw_connection(db)
    rows = (
        queries.list_all(conn)
        if status is None
        else queries.list_by_status(conn, status=status)
    )
    return [dict(row) async for row in rows]


async def _set_status(
    user_id: int,
    new_status: UserStatus,
    db: AsyncSession,
    admin: dict,
    request: Request,
    action: AuditAction,
    summary: str,
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
    await audit.record(
        conn,
        action=action,
        request=request,
        actor=admin,
        target_type=AuditTarget.USER,
        target_id=user_id,
        target_label=row["name"],
        summary=summary,
    )
    await db.commit()
    return {"id": user_id, "status": new_status}


@router.post("/{user_id}/approve")
async def approve_user(
    user_id: int,
    request: Request,
    db: AsyncSession = Depends(get_db),
    admin: dict = Depends(require_admin),
):
    return await _set_status(
        user_id, UserStatus.ACTIVE, db, admin, request, AuditAction.USER_APPROVE, "가입 승인"
    )


@router.post("/{user_id}/reject")
async def reject_user(
    user_id: int,
    request: Request,
    db: AsyncSession = Depends(get_db),
    admin: dict = Depends(require_admin),
):
    return await _set_status(
        user_id, UserStatus.REJECTED, db, admin, request, AuditAction.USER_REJECT, "가입 거절"
    )


@router.post("/{user_id}/unlock")
async def unlock_user(
    user_id: int,
    request: Request,
    db: AsyncSession = Depends(get_db),
    admin: dict = Depends(require_admin),
):
    conn = await raw_connection(db)
    row = await queries.find_by_id(conn, id=user_id)
    if row is None:
        raise Errors.not_found("사용자를 찾을 수 없습니다.")

    now = now_local()
    await queries.unlock_user(
        conn, id=user_id, unlocked_at=now, updated_at=now, updated_by=admin["id"]
    )
    await audit.record(
        conn, action=AuditAction.USER_UNLOCK, request=request, actor=admin,
        target_type=AuditTarget.USER, target_id=user_id, target_label=row["name"],
        summary="계정 잠금 해제",
    )
    await db.commit()
    return {"id": user_id, "unlocked_at": now}


@router.post("/{user_id}/reset-password")
async def reset_password(
    user_id: int,
    request: Request,
    db: AsyncSession = Depends(get_db),
    admin: dict = Depends(require_admin),
):
    """비밀번호를 초기값으로 되돌리고 다음 로그인 시 변경을 강제한다.

    본인은 대상이 아니다 — 자기 비밀번호를 초기값으로 만들 이유가 없고(설정 화면에
    변경 기능이 있다), 아래에서 세션을 전부 폐기하므로 스스로 로그아웃된 뒤 강제 변경
    화면에 갇힌다. 다른 관리자는 허용한다: 관리자가 비밀번호를 잃었을 때 psql로
    내려가지 않을 유일한 경로다.
    """
    if user_id == admin["id"]:
        raise Errors.bad_request(
            "본인 비밀번호는 이 화면에서 초기화할 수 없습니다. 설정 화면을 이용하세요."
        )

    conn = await raw_connection(db)
    row = await queries.find_by_id(conn, id=user_id)
    if row is None:
        raise Errors.not_found("사용자를 찾을 수 없습니다.")

    # argon2는 의도적으로 느린 동기 CPU 작업이다. async 핸들러에서 그대로 부르면
    # 그 시간만큼 이벤트 루프가 멈춰 SSE ping과 다른 요청까지 함께 밀린다.
    password_hash = await asyncio.to_thread(hash_password, INITIAL_PASSWORD)

    now = now_local()
    await queries.admin_reset_password(
        conn,
        id=user_id,
        password_hash=password_hash,
        unlocked_at=now,
        updated_at=now,
        updated_by=admin["id"],
    )
    # 이미 로그인된 기기가 옛 토큰으로 계속 돌아다니지 않게 끊는다 — 초기화의 동기가
    # "계정이 탈취된 것 같다"인 경우 공격자 세션을 끊는 것이 목적이다.
    await queries.revoke_all_for_user(conn, user_id=user_id, revoked_at=now, updated_at=now)
    await audit.record(
        conn, action=AuditAction.USER_RESET_PASSWORD, request=request, actor=admin,
        target_type=AuditTarget.USER, target_id=user_id, target_label=row["name"],
        summary="비밀번호 초기화 — 전 세션 폐기",
    )
    await db.commit()
    # 응답에 발급된 비밀번호를 담는다 — 지금은 고정값이지만 랜덤 발급으로 바뀌면
    # 서버만 아는 값이 된다. 화면이 처음부터 응답값을 보여주면 그때 여기만 고치면 된다.
    # unlocked_at을 함께 주는 이유는 unlock_user와 같다: 화면이 목록을 다시 불러오지 않고
    # 그 행만 갱신하므로, 서버가 정한 시각을 알려주지 않으면 '해제일시'가 비어 보인다.
    return {"id": user_id, "temp_password": INITIAL_PASSWORD, "unlocked_at": now}


@router.post("/{user_id}/reset-failures")
async def reset_failed_login(
    user_id: int,
    request: Request,
    db: AsyncSession = Depends(get_db),
    admin: dict = Depends(require_admin),
):
    conn = await raw_connection(db)
    row = await queries.find_by_id(conn, id=user_id)
    if row is None:
        raise Errors.not_found("사용자를 찾을 수 없습니다.")

    now = now_local()
    await queries.admin_reset_failed_login(
        conn, id=user_id, updated_at=now, updated_by=admin["id"]
    )
    await audit.record(
        conn, action=AuditAction.USER_RESET_FAILURES, request=request, actor=admin,
        target_type=AuditTarget.USER, target_id=user_id, target_label=row["name"],
        summary="로그인 실패 횟수 초기화",
    )
    await db.commit()
    return {"id": user_id, "failed_login_count": 0}
