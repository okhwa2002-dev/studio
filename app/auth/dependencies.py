import jwt
from fastapi import Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.security import decode_access_token
from app.constants import UserRole, UserStatus
from app.db import get_db, raw_connection
from app.queries import queries
from app.utils.errors import AppError, Errors

# must_change_password 상태에서도 통과시키는 경로. 이 셋 말고는 전부 403이다.
# - /auth/me: 프론트가 "지금 강제 변경 상태"임을 알아야 그 화면을 띄울 수 있다
# - /auth/change-password: 유일한 탈출구
# - /auth/logout: 로그아웃은 언제나 막지 않는다 (임시 비밀번호를 다시 받아야 하는
#   사용자가 화면에 갇히면 안 된다)
# /auth/policy(최소 길이)와 /auth/refresh는 current_user를 쓰지 않으므로 여기 없어도 통과한다.
# main.py가 라우터를 prefix="/api"로 등록하므로 request.url.path 기준의 절대 경로로 적는다.
_PASSWORD_CHANGE_ALLOWED = frozenset(
    {
        "/api/auth/me",
        "/api/auth/change-password",
        "/api/auth/logout",
    }
)


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
    # 관리자가 비밀번호를 초기화한 계정은 바꾸기 전까지 아무것도 못 한다. 프론트 라우팅
    # 가드는 UX일 뿐이라(RequireAuth 주석) 실제 강제는 여기서 한다 — 이게 없으면
    # API를 직접 호출해 우회할 수 있고, 그러면 "강제"라고 부를 수 없다.
    if row["must_change_password"] and request.url.path not in _PASSWORD_CHANGE_ALLOWED:
        raise AppError(
            403, "PASSWORD_CHANGE_REQUIRED", "비밀번호를 변경해야 계속할 수 있습니다."
        )
    user = dict(row)
    user.pop("password_hash", None)
    return user


def require_admin(user: dict = Depends(current_user)) -> dict:
    if user["role"] != UserRole.ADMIN:
        raise Errors.forbidden()
    return user
