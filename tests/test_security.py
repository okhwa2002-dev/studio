from datetime import datetime, timedelta, timezone

import jwt
import pytest

from app.auth.security import (
    create_access_token,
    decode_access_token,
    hash_password,
    verify_password,
)
from app.config import get_settings
from app.constants import UserRole


def test_hash_password_produces_verifiable_hash():
    hashed = hash_password("s3cret!")
    assert hashed != "s3cret!"
    assert verify_password("s3cret!", hashed) is True


def test_verify_password_rejects_wrong_password():
    hashed = hash_password("s3cret!")
    assert verify_password("wrong", hashed) is False


def test_create_and_decode_access_token_roundtrip():
    token = create_access_token(user_id=42, role=UserRole.MEMBER)
    payload = decode_access_token(token)

    assert payload["sub"] == "42"
    assert payload["role"] == UserRole.MEMBER


def test_decode_rejects_tampered_token():
    token = create_access_token(user_id=1, role=UserRole.MEMBER)
    # 토큰의 마지막 글자만 바꾸면, base64url 인코딩 마지막 그룹의 미사용(패딩) 비트에
    # 우연히 걸려 디코딩 결과 바이트가 그대로인 경우가 있어 테스트가 가끔 통과해버린다
    # (flaky). 시그니처 구간 중간의 글자를 바꿔 항상 실제 바이트가 달라지게 한다.
    idx = len(token) - 10
    tampered = token[:idx] + ("A" if token[idx] != "A" else "B") + token[idx + 1 :]

    with pytest.raises(jwt.InvalidTokenError):
        decode_access_token(tampered)


def test_decode_rejects_expired_token():
    past = datetime.now(timezone.utc) - timedelta(hours=1)
    expired_payload = {
        "sub": "1",
        "role": UserRole.MEMBER,
        "iat": past - timedelta(minutes=30),
        "exp": past,
    }
    token = jwt.encode(expired_payload, get_settings().jwt_secret, algorithm="HS256")

    with pytest.raises(jwt.InvalidTokenError):
        decode_access_token(token)
