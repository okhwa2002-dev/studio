import hashlib
import secrets
from datetime import datetime, timedelta, timezone

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError

from app.config import get_settings

ACCESS_TOKEN_MINUTES = 30

_hasher = PasswordHasher()

# 관리자가 비밀번호를 초기화할 때 설정되는 고정 비밀번호. 초기화가 must_change_password를
# 켜므로, 이 값이 계정에 남아 있는 구간은 사용자가 첫 로그인해 바꾸기 전까지다.
# 추후 랜덤 발급으로 대체한다 — 이 상수 대신 생성 함수를 쓰면 호출부와 응답 형태는
# 그대로 둘 수 있다. password_min_len 검증은 거치지 않는다(즉시 변경이 강제되고,
# 새 비밀번호는 정책을 통과해야 한다).
INITIAL_PASSWORD = "qwer1234"


def hash_password(password: str) -> str:
    return _hasher.hash(password)


def verify_password(password: str, password_hash: str) -> bool:
    try:
        return _hasher.verify(password_hash, password)
    except VerifyMismatchError:
        return False


def create_access_token(user_id: int, role: str) -> str:
    # JWT의 iat/exp는 실제 UTC 절대시각이어야 한다(PyJWT가 naive datetime을
    # UTC로 간주해 처리). 프로젝트의 로컬시간 저장 규칙(now_local())과는 별개.
    now = datetime.now(timezone.utc)
    payload = {
        "sub": str(user_id),
        "role": role,
        "iat": now,
        "exp": now + timedelta(minutes=ACCESS_TOKEN_MINUTES),
    }
    return jwt.encode(payload, get_settings().jwt_secret, algorithm="HS256")


def decode_access_token(token: str) -> dict:
    return jwt.decode(token, get_settings().jwt_secret, algorithms=["HS256"])


REFRESH_TOKEN_DAYS = 14


def generate_refresh_token() -> str:
    return secrets.token_urlsafe(48)


def hash_refresh_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()
