from app.auth.security import hash_password
from app.queries import queries
from app.utils.time import now_local


async def ensure_admin_seeded(conn, email: str, password: str) -> bool:
    """email의 사용자가 없으면 role=admin, status=active로 생성한다.

    이미 존재하면 아무 것도 하지 않고 False를 반환한다(재실행해도 안전).
    """
    existing = await queries.find_by_email(conn, email=email)
    if existing is not None:
        return False

    now = now_local()
    await queries.insert_user(
        conn,
        email=email,
        password_hash=hash_password(password),
        role="admin",
        status="active",
        created_at=now,
        updated_at=now,
    )
    return True
