import jwt
from fastapi import Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.security import decode_access_token
from app.constants import UserRole, UserStatus
from app.db import get_db, raw_connection
from app.queries import queries
from app.utils.errors import Errors


async def current_user(request: Request, db: AsyncSession = Depends(get_db)) -> dict:
    token = request.cookies.get("access_token")
    if not token:
        raise Errors.unauthorized()

    try:
        payload = decode_access_token(token)
    except jwt.InvalidTokenError:
        raise Errors.unauthorized("인증 정보가 유효하지 않습니다.")

    conn = await raw_connection(db)
    row = await queries.find_by_id(conn, id=int(payload["sub"]))
    if row is None or row["status"] != UserStatus.ACTIVE:
        raise Errors.unauthorized("인증 정보가 유효하지 않습니다.")
    user = dict(row)
    user.pop("password_hash", None)
    return user


def require_admin(user: dict = Depends(current_user)) -> dict:
    if user["role"] != UserRole.ADMIN:
        raise Errors.forbidden()
    return user
