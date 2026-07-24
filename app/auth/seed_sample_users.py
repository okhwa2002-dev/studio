from urllib.parse import urlsplit

from app.auth.security import hash_password
from app.constants import UserRole, UserStatus
from app.queries import queries
from app.utils.time import now_local

SAMPLE_PASSWORD = "password123"

# 이메일이 고정이라는 점이 멱등성의 근거다. 이미 있는 이메일은 건너뛰므로
# 몇 번을 돌려도 중복이 생기지 않고, 승인해 둔 샘플 계정의 상태도 되돌아가지 않는다.
SAMPLE_USERS: list[tuple[str, str, UserRole, UserStatus]] = [
    ("sample-pending1@example.com", "김대기", UserRole.MEMBER, UserStatus.PENDING),
    ("sample-pending2@example.com", "이대기", UserRole.MEMBER, UserStatus.PENDING),
    ("sample-pending3@example.com", "박대기", UserRole.MEMBER, UserStatus.PENDING),
    ("sample-pending4@example.com", "최대기", UserRole.MEMBER, UserStatus.PENDING),
    ("sample-pending5@example.com", "정대기", UserRole.MEMBER, UserStatus.PENDING),
    ("sample-member1@example.com", "홍길동", UserRole.MEMBER, UserStatus.ACTIVE),
    ("sample-member2@example.com", "김철수", UserRole.MEMBER, UserStatus.ACTIVE),
    ("sample-rejected1@example.com", "오거절", UserRole.MEMBER, UserStatus.REJECTED),
]


def is_local_database(database_url: str) -> bool:
    """DATABASE_URL이 로컬 호스트를 가리키는지 판별한다.

    문자열 포함 검사(`"localhost" in url`)는 db.localhost.evil.com 같은 주소에 속는다.
    반드시 호스트명을 파싱해서 비교한다.
    """
    host = urlsplit(database_url).hostname
    return host in ("localhost", "127.0.0.1")


async def ensure_sample_users_seeded(conn) -> int:
    """샘플 사용자를 생성하고 생성한 개수를 반환한다.

    이미 존재하는 이메일은 건너뛴다(재실행해도 안전).
    """
    now = now_local()
    # 8명이 같은 비밀번호를 쓰므로 해시는 한 번만 계산한다(argon2는 의도적으로 느리다).
    password_hash = hash_password(SAMPLE_PASSWORD)

    created = 0
    for email, name, role, status in SAMPLE_USERS:
        if await queries.find_by_email(conn, email=email) is not None:
            continue
        await queries.insert_user(
            conn,
            email=email,
            name=name,
            password_hash=password_hash,
            role=role,
            status=status,
            created_at=now,
            updated_at=now,
        )
        created += 1

    return created
