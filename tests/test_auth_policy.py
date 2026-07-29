import json

from app.db import raw_connection
from app.queries import queries
from app.runtime_settings import invalidate_runtime_settings
from app.utils.time import now_local


async def test_policy_is_readable_without_login(client):
    """회원가입 화면은 로그인 전에 이 값을 필요로 한다."""
    resp = await client.get("/api/auth/policy")
    assert resp.status_code == 200
    assert resp.json() == {"password_min_len": 8}


async def test_policy_follows_runtime_setting(client, db_session):
    conn = await raw_connection(db_session)
    await queries.upsert_setting(
        conn, key="password_min_len", value=json.dumps(16), now=now_local(), actor_id=None
    )
    invalidate_runtime_settings()

    resp = await client.get("/api/auth/policy")
    assert resp.json() == {"password_min_len": 16}


async def test_register_rejects_password_shorter_than_minimum(client):
    resp = await client.post(
        "/api/auth/register",
        json={"email": "short-pw@example.com", "password": "pw12345", "name": "홍길동"},
    )
    assert resp.status_code == 400
    assert resp.json()["code"] == "WEAK_PASSWORD"


async def test_register_accepts_password_at_the_minimum(client):
    """경계값: 8자는 허용이다."""
    resp = await client.post(
        "/api/auth/register",
        json={"email": "exact-pw@example.com", "password": "pw123456", "name": "홍길동"},
    )
    assert resp.status_code == 201


async def test_register_minimum_follows_runtime_setting(client, db_session):
    conn = await raw_connection(db_session)
    await queries.upsert_setting(
        conn, key="password_min_len", value=json.dumps(12), now=now_local(), actor_id=None
    )
    invalidate_runtime_settings()

    resp = await client.post(
        "/api/auth/register",
        json={"email": "raised-min@example.com", "password": "pw123456", "name": "홍길동"},
    )
    assert resp.status_code == 400
    assert resp.json()["code"] == "WEAK_PASSWORD"
