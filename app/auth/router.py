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
from app.db import get_db, raw_connection
from app.queries import queries
from app.utils.errors import Errors
from app.utils.time import now_local

router = APIRouter(prefix="/auth", tags=["auth"])

# 이메일이 존재하지 않는 경우에도 verify_password(Argon2, 의도적으로 느림)를 호출해
# 동일한 연산 비용을 지불하기 위한 더미 해시. 이게 없으면 "이메일 없음" 응답이
# "이메일은 있으나 비밀번호 틀림" 응답보다 눈에 띄게 빨라져, 응답 시간을 통해
# 등록된 이메일을 추측하는 타이밍 사이드채널 공격이 가능해진다.
# (주의: 아래 로그인 로직에서 `row is None or not verify_password(...)`처럼
#  단축 평가로 "단순화"하면 이 방어가 무력화되니 절대 합치지 말 것.)
_DUMMY_PASSWORD_HASH = hash_password("dummy-password-for-timing-safety")


class RegisterRequest(BaseModel):
    email: str
    password: str


@router.post("/register", status_code=201)
async def register(body: RegisterRequest, db: AsyncSession = Depends(get_db)):
    email = body.email.strip().lower()
    conn = await raw_connection(db)
    existing = await queries.find_by_email(conn, email=email)
    if existing is not None:
        raise Errors.conflict("이미 등록된 이메일입니다.")

    now = now_local()
    try:
        user_id = await queries.insert_user(
            conn,
            email=email,
            password_hash=hash_password(body.password),
            role="member",
            status="pending",
            created_at=now,
            updated_at=now,
        )
    except asyncpg.exceptions.UniqueViolationError:
        # find_by_email 확인 이후, insert 사이의 경합으로 동시에 같은 이메일이
        # 등록된 경우(동시 요청/빠른 중복 제출). DB 유니크 제약이 잡아준 것을
        # 500이 아닌 409 CONFLICT로 변환한다.
        raise Errors.conflict("이미 등록된 이메일입니다.")
    await db.commit()
    return {"id": user_id, "status": "pending"}


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
async def login(body: LoginRequest, response: Response, db: AsyncSession = Depends(get_db)):
    conn = await raw_connection(db)
    email = body.email.strip().lower()
    row = await queries.find_by_email(conn, email=email)
    if row is None:
        # 더미 해시로라도 verify_password를 호출해 존재하는 계정과 동일한
        # 연산 비용을 지불한다(결과는 사용하지 않음). 타이밍 사이드채널 방지.
        verify_password(body.password, _DUMMY_PASSWORD_HASH)
        raise Errors.unauthorized("이메일 또는 비밀번호가 올바르지 않습니다.")
    if not verify_password(body.password, row["password_hash"]):
        raise Errors.unauthorized("이메일 또는 비밀번호가 올바르지 않습니다.")
    if row["status"] != "active":
        raise Errors.forbidden("관리자 승인 대기 중이거나 비활성화된 계정입니다.")

    access_token = create_access_token(row["id"], row["role"])
    refresh_token = generate_refresh_token()
    now = now_local()
    await queries.insert_refresh_token(
        conn,
        user_id=row["id"],
        token_hash=hash_refresh_token(refresh_token),
        expires_at=now + timedelta(days=REFRESH_TOKEN_DAYS),
        created_at=now,
        updated_at=now,
    )
    await db.commit()

    _set_auth_cookies(response, access_token, refresh_token)
    return {"id": row["id"], "email": row["email"], "role": row["role"]}


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
        await db.commit()
        raise Errors.unauthorized("토큰이 재사용되어 모든 세션을 종료했습니다. 다시 로그인해주세요.")
    if row["expires_at"] < now:
        raise Errors.unauthorized("토큰이 만료되었습니다.")

    user_row = await queries.find_by_id(conn, id=row["user_id"])
    if user_row is None or user_row["status"] != "active":
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
            await db.commit()

    response.delete_cookie("access_token")
    response.delete_cookie("refresh_token")
    return {"status": "ok"}


@router.get("/me")
async def me(user: dict = Depends(current_user)):
    # current_user가 쿠키 검증·상태 확인·password_hash 제거까지 이미 수행한다.
    # 여기서는 프론트가 실제로 쓰는 필드만 골라 내보낸다(감사 컬럼·approved_by 등 미노출).
    return {"id": user["id"], "email": user["email"], "role": user["role"]}
