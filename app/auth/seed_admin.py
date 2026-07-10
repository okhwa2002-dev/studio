from app.auth.security import hash_password
from app.queries import queries
from app.utils.time import now_local


async def ensure_admin_seeded(conn, email: str, password: str) -> bool:
    """email의 사용자가 없으면 role=admin, status=active로 생성한다.

    이미 존재하면 아무 것도 하지 않고 False를 반환한다(재실행해도 안전).
    """
    # register/login과 동일하게 정규화해야, .env의 대소문자/공백이 달라도
    # 항상 같은 계정으로 취급된다(정규화 안 하면 로그인 시 불일치 가능).
    email = email.strip().lower()

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
