import re

from app.db import raw_connection
from app.models.user import User
from app.queries import queries

_MSG = "인증코드를 발송했습니다."


async def _make_user(db_session, email, status="ACTIVE") -> int:
    user = User(email=email, password_hash="x", name="테스트", role="MEMBER", status=status)
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    return user.id


async def test_request_stores_hashed_code_and_returns_uniform_message(client, db_session):
    await _make_user(db_session, "req-active@example.com")

    resp = await client.post("/api/auth/password-reset/request", json={"email": "req-active@example.com"})
    assert resp.status_code == 200
    assert resp.json() == {"message": _MSG}

    conn = await raw_connection(db_session)
    user = await queries.find_by_email(conn, email="req-active@example.com")
    row = await queries.find_active_reset_code(conn, user_id=user["id"])
    assert row is not None
    # 코드는 6자리 숫자 문자열로 그대로 저장된다(앞자리 0 보존).
    assert isinstance(row["code"], str)
    assert len(row["code"]) == 6
    assert row["code"].isdigit()


async def test_request_never_returns_the_code(client, db_session):
    await _make_user(db_session, "req-nocode@example.com")

    resp = await client.post("/api/auth/password-reset/request", json={"email": "req-nocode@example.com"})
    # 응답 본문 어디에도 6자리 숫자 코드가 없다(이 기능의 안전장치).
    assert not re.search(r"\b\d{6}\b", resp.text)


async def test_request_unknown_email_returns_same_message_and_stores_nothing(client, db_session):
    resp = await client.post("/api/auth/password-reset/request", json={"email": "nobody@example.com"})
    assert resp.status_code == 200
    assert resp.json() == {"message": _MSG}


async def test_request_disabled_account_gets_no_code_but_same_message(client, db_session):
    uid = await _make_user(db_session, "req-disabled@example.com", status="DISABLED")

    resp = await client.post("/api/auth/password-reset/request", json={"email": "req-disabled@example.com"})
    assert resp.status_code == 200
    assert resp.json() == {"message": _MSG}

    conn = await raw_connection(db_session)
    assert await queries.find_active_reset_code(conn, user_id=uid) is None


async def test_request_invalidates_previous_code(client, db_session):
    uid = await _make_user(db_session, "req-twice@example.com")
    conn = await raw_connection(db_session)

    await client.post("/api/auth/password-reset/request", json={"email": "req-twice@example.com"})
    first = await queries.find_active_reset_code(conn, user_id=uid)
    await client.post("/api/auth/password-reset/request", json={"email": "req-twice@example.com"})
    second = await queries.find_active_reset_code(conn, user_id=uid)

    # 활성 코드는 항상 최신 1개. 이전 코드는 무효화되어 최신 것과 다른 행이다.
    assert second["id"] != first["id"]
