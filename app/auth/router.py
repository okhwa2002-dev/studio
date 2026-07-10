from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.security import hash_password
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
