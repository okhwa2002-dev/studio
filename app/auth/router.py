from datetime import timedelta

from fastapi import APIRouter, Depends, Response
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

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


class RegisterRequest(BaseModel):
    email: str
    password: str


@router.post("/register", status_code=201)
async def register(body: RegisterRequest, db: AsyncSession = Depends(get_db)):
    conn = await raw_connection(db)
    existing = await queries.find_by_email(conn, email=body.email)
    if existing is not None:
        raise Errors.conflict("이미 등록된 이메일입니다.")

    now = now_local()
    user_id = await queries.insert_user(
        conn,
        email=body.email,
        password_hash=hash_password(body.password),
        role="member",
        status="pending",
        created_at=now,
        updated_at=now,
    )
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
    row = await queries.find_by_email(conn, email=body.email)
    if row is None or not verify_password(body.password, row["password_hash"]):
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
