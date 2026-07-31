from datetime import timedelta

import asyncpg
from fastapi import APIRouter, Depends, Request, Response
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import current_user
from app.auth.security import (
    ACCESS_TOKEN_MINUTES,
    REFRESH_TOKEN_DAYS,
    create_access_token,
    generate_refresh_token,
    hash_password,
    hash_refresh_token,
    verify_password,
)
from app.config import get_settings
from app.constants import AuditAction, AuditTarget, UserRole, UserStatus
from app.core import audit
from app.db import get_db, raw_connection
from app.queries import queries
from app.runtime_settings import get_runtime_settings
from app.utils.errors import AppError, Errors
from app.utils.time import now_local

router = APIRouter(prefix="/auth", tags=["auth"])

# 이메일이 존재하지 않는 경우에도 verify_password(Argon2, 의도적으로 느림)를 호출해
# 동일한 연산 비용을 지불하기 위한 더미 해시. 이게 없으면 "이메일 없음" 응답이
# "이메일은 있으나 비밀번호 틀림" 응답보다 눈에 띄게 빨라져, 응답 시간을 통해
# 등록된 이메일을 추측하는 타이밍 사이드채널 공격이 가능해진다.
# (주의: 아래 로그인 로직에서 `row is None or not verify_password(...)`처럼
#  단축 평가로 "단순화"하면 이 방어가 무력화되니 절대 합치지 말 것.)
_DUMMY_PASSWORD_HASH = hash_password("dummy-password-for-timing-safety")


_NAME_MAX_LEN = 50


class RegisterRequest(BaseModel):
    email: str
    password: str
    name: str


@router.get("/policy")
async def policy(db: AsyncSession = Depends(get_db)):
    """회원가입·비밀번호 변경 화면이 쓰는 공개 정책값.

    회원가입은 로그인 전 화면이라 /auth/me로는 전달할 수 없고, 일반 사용자에게
    관리자 설정 API를 열 수도 없다. 최소 길이는 가입을 시도하면 어차피 드러나는
    값이라 공개해도 잃을 것이 없다.
    """
    conn = await raw_connection(db)
    return {"password_min_len": (await get_runtime_settings(conn)).password_min_len}


@router.post("/register", status_code=201)
async def register(body: RegisterRequest, request: Request, db: AsyncSession = Depends(get_db)):
    email = body.email.strip().lower()
    # 이름은 표시용이라 lower()하지 않는다(email과 다르다). 공백만 입력은 거부.
    name = body.name.strip()
    if not name or len(name) > _NAME_MAX_LEN:
        raise AppError(400, "INVALID_NAME", "이름은 1~50자로 입력해 주세요.")
    conn = await raw_connection(db)

    # 비밀번호 변경과 같은 규칙·같은 에러 코드를 쓴다. 가입 경로에만 검증이 없어서
    # 1자 비밀번호로도 계정이 만들어지던 구멍을 막는다.
    runtime = await get_runtime_settings(conn)
    min_len = runtime.password_min_len
    if len(body.password) < min_len:
        raise AppError(400, "WEAK_PASSWORD", f"비밀번호는 {min_len}자 이상이어야 합니다.")

    existing = await queries.find_by_email(conn, email=email)
    if existing is not None:
        raise Errors.conflict("이미 등록된 이메일입니다.")

    # 자동 승인이 켜져 있으면 승인 대기를 건너뛴다. 이미 PENDING인 사용자에게는
    # 소급되지 않는다 — 설정은 이후 가입에만 적용된다.
    status = UserStatus.ACTIVE if runtime.signup_auto_approve else UserStatus.PENDING

    now = now_local()
    try:
        user_id = await queries.insert_user(
            conn,
            email=email,
            name=name,
            password_hash=hash_password(body.password),
            role=UserRole.MEMBER,
            status=status,
            created_at=now,
            updated_at=now,
        )
    except asyncpg.exceptions.UniqueViolationError:
        # find_by_email 확인 이후, insert 사이의 경합으로 동시에 같은 이메일이
        # 등록된 경우(동시 요청/빠른 중복 제출). DB 유니크 제약이 잡아준 것을
        # 500이 아닌 409 CONFLICT로 변환한다.
        raise Errors.conflict("이미 등록된 이메일입니다.")
    await audit.record(
        conn,
        action=AuditAction.REGISTER,
        request=request,
        actor={"id": user_id, "email": email, "name": name},
        target_type=AuditTarget.USER,
        target_id=user_id,
        target_label=name,
        summary="가입 (자동 승인)" if status == UserStatus.ACTIVE else "가입 신청 (승인 대기)",
    )
    await db.commit()
    return {"id": user_id, "status": status}


class LoginRequest(BaseModel):
    email: str
    password: str


def _set_auth_cookies(response: Response, access_token: str, refresh_token: str) -> None:
    secure = get_settings().secure_cookies
    response.set_cookie(
        "access_token",
        access_token,
        httponly=True,
        secure=secure,
        samesite="lax",
        max_age=ACCESS_TOKEN_MINUTES * 60,
    )
    response.set_cookie(
        "refresh_token",
        refresh_token,
        httponly=True,
        secure=secure,
        samesite="lax",
        max_age=REFRESH_TOKEN_DAYS * 24 * 60 * 60,
    )


@router.post("/login")
async def login(
    body: LoginRequest,
    request: Request,
    response: Response,
    db: AsyncSession = Depends(get_db),
):
    conn = await raw_connection(db)
    email = body.email.strip().lower()
    row = await queries.find_by_email(conn, email=email)
    if row is None:
        # 더미 해시로라도 verify_password를 호출해 존재하는 계정과 동일한 연산 비용을 지불한다
        # (타이밍 사이드채널 방지). 셀 계정이 없으므로 카운트 없음.
        verify_password(body.password, _DUMMY_PASSWORD_HASH)
        # 없는 이메일도 문자열 그대로 남긴다 — 계정 열거 공격은 "없는 이메일 수백 건
        # 시도"라는 모양으로만 드러나므로, 이 값이 없으면 패턴 자체가 보이지 않는다.
        # record_failure인 이유: 아래 raise로 끝나 커밋에 도달하지 못한다.
        await audit.record_failure(
            db,
            action=AuditAction.LOGIN_FAILURE,
            request=request,
            actor_email=email,
            success=False,
            summary="존재하지 않는 계정",
        )
        raise Errors.unauthorized("이메일 또는 비밀번호가 올바르지 않습니다.")

    now = now_local()
    if not verify_password(body.password, row["password_hash"]):
        # 실패 카운트 증가. 임계치 도달 시 잠근다. 이미 잠겼으면 잠금 시각을 유지한다.
        new_count = row["failed_login_count"] + 1
        if row["locked_at"] is not None:
            new_locked_at = row["locked_at"]
        elif new_count >= (await get_runtime_settings(conn)).failed_login_limit:
            new_locked_at = now
        else:
            new_locked_at = None
        await queries.record_failed_login(
            conn, id=row["id"], failed_login_count=new_count, locked_at=new_locked_at, updated_at=now
        )
        # 이 경로에는 아래 db.commit()이 있으므로 record로 충분하다.
        await audit.record(
            conn,
            action=AuditAction.LOGIN_FAILURE,
            request=request,
            actor=row,
            success=False,
            summary="비밀번호 불일치",
        )
        # 잠기는 순간에만 한 번 남긴다. 이미 잠긴 계정에 계속 시도하면 LOGIN_FAILURE만 쌓인다.
        if row["locked_at"] is None and new_locked_at is not None:
            await audit.record(
                conn,
                action=AuditAction.ACCOUNT_LOCKED,
                request=request,
                actor=row,
                target_type=AuditTarget.USER,
                target_id=row["id"],
                target_label=row["name"],
                success=False,
                summary=f"연속 로그인 실패 {new_count}회로 잠김",
            )
        await db.commit()
        # 오답은 잠김 여부와 무관하게 항상 통일 401. 공격자에게 잠김을 드러내지 않는다.
        raise Errors.unauthorized("이메일 또는 비밀번호가 올바르지 않습니다.")

    # 비밀번호는 맞음. 잠김은 status와 별개로 먼저 막는다(진짜 사용자에게만 423).
    if row["locked_at"] is not None:
        await audit.record_failure(
            db,
            action=AuditAction.LOGIN_FAILURE,
            request=request,
            actor=row,
            success=False,
            summary="잠긴 계정",
        )
        raise Errors.locked()
    if row["status"] != UserStatus.ACTIVE:
        await audit.record_failure(
            db,
            action=AuditAction.LOGIN_FAILURE,
            request=request,
            actor=row,
            success=False,
            summary="승인 대기·비활성 계정",
        )
        raise Errors.forbidden("관리자 승인 대기 중이거나 비활성화된 계정입니다.")

    if row["failed_login_count"] > 0:
        await queries.reset_failed_login(conn, id=row["id"], updated_at=now)

    access_token = create_access_token(row["id"], row["role"])
    refresh_token = generate_refresh_token()
    await queries.insert_refresh_token(
        conn,
        user_id=row["id"],
        token_hash=hash_refresh_token(refresh_token),
        expires_at=now + timedelta(days=REFRESH_TOKEN_DAYS),
        created_at=now,
        updated_at=now,
    )
    await audit.record(conn, action=AuditAction.LOGIN_SUCCESS, request=request, actor=row)
    await db.commit()

    _set_auth_cookies(response, access_token, refresh_token)
    # 강제 변경 상태여도 로그인 자체는 성공한다 — 실패시키면 비밀번호를 바꿀 방법이 없다.
    # 차단은 current_user의 게이트가 맡고, 프론트는 이 플래그로 변경 화면을 띄운다.
    # (프론트의 login은 이 응답을 그대로 쓰고 /auth/me를 다시 부르지 않으므로 여기에도 필요하다)
    return {
        "id": row["id"],
        "email": row["email"],
        "role": row["role"],
        "name": row["name"],
        "must_change_password": row["must_change_password"],
    }


@router.post("/refresh")
async def refresh(request: Request, response: Response, db: AsyncSession = Depends(get_db)):
    token = request.cookies.get("refresh_token")
    if not token:
        raise Errors.unauthorized()

    conn = await raw_connection(db)
    token_hash = hash_refresh_token(token)
    row = await queries.find_by_token_hash(conn, token_hash=token_hash)
    now = now_local()

    if row is None:
        raise Errors.unauthorized("유효하지 않은 토큰입니다.")
    if row["revoked_at"] is not None:
        # 이미 회전되어 폐기된 토큰이 재사용됨 → 탈취 의심, 해당 사용자의 모든 세션 폐기
        await queries.revoke_all_for_user(conn, user_id=row["user_id"], revoked_at=now, updated_at=now)
        # 정상 갱신은 기록하지 않는다(몇 분마다 발생해 목록을 덮는다). 이 분기만 남긴다 —
        # 감사 로그가 존재하는 이유에 가장 가까운 사건이다.
        user_row = await queries.find_by_id(conn, id=row["user_id"])
        await audit.record(
            conn,
            action=AuditAction.TOKEN_REUSE_DETECTED,
            request=request,
            actor=user_row,
            target_type=AuditTarget.USER,
            target_id=row["user_id"],
            target_label=user_row["name"] if user_row is not None else None,
            success=False,
            summary="폐기된 리프레시 토큰 재사용 — 전 세션 폐기",
        )
        await db.commit()
        raise Errors.unauthorized("토큰이 재사용되어 모든 세션을 종료했습니다. 다시 로그인해주세요.")
    if row["expires_at"] < now:
        raise Errors.unauthorized("토큰이 만료되었습니다.")

    user_row = await queries.find_by_id(conn, id=row["user_id"])
    if user_row is None or user_row["status"] != UserStatus.ACTIVE:
        raise Errors.unauthorized()

    await queries.revoke_by_id(conn, id=row["id"], revoked_at=now, updated_at=now)
    new_refresh_token = generate_refresh_token()
    await queries.insert_refresh_token(
        conn,
        user_id=user_row["id"],
        token_hash=hash_refresh_token(new_refresh_token),
        expires_at=now + timedelta(days=REFRESH_TOKEN_DAYS),
        created_at=now,
        updated_at=now,
    )
    await db.commit()

    access_token = create_access_token(user_row["id"], user_row["role"])
    _set_auth_cookies(response, access_token, new_refresh_token)
    return {"id": user_row["id"]}


@router.post("/logout")
async def logout(request: Request, response: Response, db: AsyncSession = Depends(get_db)):
    token = request.cookies.get("refresh_token")
    if token:
        conn = await raw_connection(db)
        row = await queries.find_by_token_hash(conn, token_hash=hash_refresh_token(token))
        if row is not None and row["revoked_at"] is None:
            now = now_local()
            await queries.revoke_by_id(conn, id=row["id"], revoked_at=now, updated_at=now)
            # 토큰 행에는 이메일·이름이 없다. 스냅샷을 채우려면 사용자를 한 번 읽어야 한다.
            user_row = await queries.find_by_id(conn, id=row["user_id"])
            await audit.record(
                conn, action=AuditAction.LOGOUT, request=request, actor=user_row
            )
            await db.commit()

    response.delete_cookie("access_token")
    response.delete_cookie("refresh_token")
    return {"status": "ok"}


@router.get("/me")
async def me(user: dict = Depends(current_user)):
    # current_user가 쿠키 검증·상태 확인·password_hash 제거까지 이미 수행한다.
    # 여기서는 프론트가 실제로 쓰는 필드만 골라 내보낸다(감사 컬럼·approved_by 등 미노출).
    # must_change_password는 게이트가 이 경로만은 통과시키는 이유다 — 프론트가 세션을
    # 복원할 때 강제 변경 상태임을 알아야 그 화면으로 보낼 수 있다.
    return {
        "id": user["id"],
        "email": user["email"],
        "role": user["role"],
        "name": user["name"],
        "must_change_password": user["must_change_password"],
    }


class ChangePasswordRequest(BaseModel):
    current_password: str
    new_password: str


@router.post("/change-password")
async def change_password(
    body: ChangePasswordRequest,
    request: Request,
    response: Response,
    user: dict = Depends(current_user),
    db: AsyncSession = Depends(get_db),
):
    conn = await raw_connection(db)
    # current_user는 password_hash를 지운 dict라, 해시가 필요해 다시 조회한다.
    row = await queries.find_by_id(conn, id=user["id"])
    if row is None or not verify_password(body.current_password, row["password_hash"]):
        raise AppError(400, "INVALID_PASSWORD", "현재 비밀번호가 올바르지 않습니다.")
    min_len = (await get_runtime_settings(conn)).password_min_len
    if len(body.new_password) < min_len:
        raise AppError(400, "WEAK_PASSWORD", f"새 비밀번호는 {min_len}자 이상이어야 합니다.")
    if verify_password(body.new_password, row["password_hash"]):
        raise AppError(400, "SAME_PASSWORD", "새 비밀번호가 현재 비밀번호와 같습니다.")

    now = now_local()
    await queries.update_password(
        conn,
        id=user["id"],
        password_hash=hash_password(body.new_password),
        updated_at=now,
        updated_by=user["id"],
    )
    # 다른 기기 세션은 모두 끊고(탈취 대응) 곧바로 현재 기기용 새 세션을 발급해 유지한다.
    # revoke_all → insert 순서라, 방금 만든 새 토큰은 폐기되지 않는다.
    await queries.revoke_all_for_user(conn, user_id=user["id"], revoked_at=now, updated_at=now)
    refresh_token = generate_refresh_token()
    await queries.insert_refresh_token(
        conn,
        user_id=user["id"],
        token_hash=hash_refresh_token(refresh_token),
        expires_at=now + timedelta(days=REFRESH_TOKEN_DAYS),
        created_at=now,
        updated_at=now,
    )
    await audit.record(
        conn,
        action=AuditAction.PASSWORD_CHANGE,
        request=request,
        actor=user,
        target_type=AuditTarget.USER,
        target_id=user["id"],
        target_label=user["name"],
        summary="비밀번호 변경 — 다른 기기 세션 폐기",
    )
    await db.commit()

    access_token = create_access_token(user["id"], user["role"])
    _set_auth_cookies(response, access_token, refresh_token)
    return {"status": "ok"}
