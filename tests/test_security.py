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


def test_hash_password_produces_verifiable_hash():
    hashed = hash_password("s3cret!")
    assert hashed != "s3cret!"
    assert verify_password("s3cret!", hashed) is True


def test_verify_password_rejects_wrong_password():
    hashed = hash_password("s3cret!")
    assert verify_password("wrong", hashed) is False


def test_create_and_decode_access_token_roundtrip():
    token = create_access_token(user_id=42, role="member")
    payload = decode_access_token(token)

    assert payload["sub"] == "42"
    assert payload["role"] == "member"


def test_decode_rejects_tampered_token():
    token = create_access_token(user_id=1, role="member")
    tampered = token[:-1] + ("A" if token[-1] != "A" else "B")

    with pytest.raises(jwt.InvalidTokenError):
        decode_access_token(tampered)


def test_decode_rejects_expired_token():
    past = datetime.now(timezone.utc) - timedelta(hours=1)
    expired_payload = {
        "sub": "1",
        "role": "member",
        "iat": past - timedelta(minutes=30),
        "exp": past,
    }
    token = jwt.encode(expired_payload, get_settings().jwt_secret, algorithm="HS256")

    with pytest.raises(jwt.InvalidTokenError):
        decode_access_token(token)
