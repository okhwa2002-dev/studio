from datetime import timedelta

from app.auth.security import verify_password
from app.constants import AuditAction
from app.db import raw_connection
from app.models.user import User
from app.queries import queries
from app.utils.time import now_local

_FAIL = "코드가 올바르지 않거나 만료되었습니다."
_URL = "/api/auth/password-reset/confirm"


async def _user_with_code(db_session, email, code="123456", *, expired=False, status="ACTIVE"):
    user = User(email=email, password_hash="old-hash", name="테스트", role="MEMBER", status=status)
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)

    conn = await raw_connection(db_session)
    now = now_local()
    expires = now - timedelta(minutes=1) if expired else now + timedelta(minutes=10)
    code_id = await queries.insert_reset_code(
        conn,
        user_id=user.id,
        code=code,
        expires_at=expires,
        created_at=now,
        updated_at=now,
    )
    await db_session.commit()
    return user.id, code_id


async def test_confirm_with_correct_code_changes_password(client, db_session):
    uid, _ = await _user_with_code(db_session, "conf-ok@example.com", code="654321")

    resp = await client.post(
        _URL,
        json={"email": "conf-ok@example.com", "code": "654321", "new_password": "brand-new-pw"},
    )
    assert resp.status_code == 200

    conn = await raw_connection(db_session)
    row = await queries.find_by_id(conn, id=uid)
    assert verify_password("brand-new-pw", row["password_hash"])
    # 코드는 소비되어 더는 활성이 아니다.
    assert await queries.find_active_reset_code(conn, user_id=uid) is None


async def test_confirm_revokes_refresh_tokens(client, db_session):
    uid, _ = await _user_with_code(db_session, "conf-revoke@example.com", code="111111")
    conn = await raw_connection(db_session)
    now = now_local()
    await queries.insert_refresh_token(
        conn,
        user_id=uid,
        token_hash="tok",
        expires_at=now + timedelta(days=1),
        created_at=now,
        updated_at=now,
    )
    await db_session.commit()

    await client.post(
        _URL,
        json={"email": "conf-revoke@example.com", "code": "111111", "new_password": "another-new-pw"},
    )

    row = await queries.find_by_token_hash(conn, token_hash="tok")
    assert row["revoked_at"] is not None


async def test_confirm_wrong_code_uniform_error_and_increments_attempts(client, db_session):
    uid, _ = await _user_with_code(db_session, "conf-wrong@example.com", code="222222")

    resp = await client.post(
        _URL,
        json={"email": "conf-wrong@example.com", "code": "000000", "new_password": "x-new-password"},
    )
    assert resp.status_code == 400
    assert resp.json()["code"] == "INVALID_RESET_CODE"
    assert resp.json()["message"] == _FAIL

    conn = await raw_connection(db_session)
    row = await queries.find_active_reset_code(conn, user_id=uid)
    assert row["attempts"] == 1
    # 비밀번호는 그대로다(픽스처가 심은 원문 해시가 바뀌지 않았다).
    user = await queries.find_by_id(conn, id=uid)
    assert user["password_hash"] == "old-hash"


async def test_confirm_expired_code_uniform_error(client, db_session):
    await _user_with_code(db_session, "conf-exp@example.com", code="333333", expired=True)

    resp = await client.post(
        _URL,
        json={"email": "conf-exp@example.com", "code": "333333", "new_password": "x-new-password"},
    )
    assert resp.status_code == 400
    assert resp.json()["message"] == _FAIL


async def test_confirm_exhausted_attempts_invalidates_code(client, db_session):
    uid, _ = await _user_with_code(db_session, "conf-exhaust@example.com", code="444444")

    for _ in range(5):
        await client.post(
            _URL,
            json={"email": "conf-exhaust@example.com", "code": "000000", "new_password": "x-new-password"},
        )

    conn = await raw_connection(db_session)
    # 5회 실패로 코드가 무효화되어, 이후 올바른 코드도 거부된다.
    assert await queries.find_active_reset_code(conn, user_id=uid) is None
    resp = await client.post(
        _URL,
        json={"email": "conf-exhaust@example.com", "code": "444444", "new_password": "x-new-password"},
    )
    assert resp.status_code == 400


async def test_confirm_weak_password_rejected(client, db_session):
    await _user_with_code(db_session, "conf-weak@example.com", code="555555")

    resp = await client.post(
        _URL,
        json={"email": "conf-weak@example.com", "code": "555555", "new_password": "short"},
    )
    assert resp.status_code == 400
    assert resp.json()["code"] == "WEAK_PASSWORD"


async def test_confirm_leading_zero_code_works(client, db_session):
    # VARCHAR 저장의 핵심 — 앞자리 0이 보존되어 "012345"가 그대로 매칭된다.
    uid, _ = await _user_with_code(db_session, "conf-zero@example.com", code="012345")

    resp = await client.post(
        _URL,
        json={"email": "conf-zero@example.com", "code": "012345", "new_password": "zero-new-pw"},
    )
    assert resp.status_code == 200

    conn = await raw_connection(db_session)
    assert verify_password("zero-new-pw", (await queries.find_by_id(conn, id=uid))["password_hash"])


async def test_confirm_unknown_email_uniform_error(client, db_session):
    resp = await client.post(
        _URL,
        json={"email": "ghost@example.com", "code": "123456", "new_password": "x-new-password"},
    )
    assert resp.status_code == 400
    assert resp.json()["message"] == _FAIL


async def test_confirm_records_audit_on_success(client, db_session):
    uid, _ = await _user_with_code(db_session, "conf-audit@example.com", code="666666")

    await client.post(
        _URL,
        json={"email": "conf-audit@example.com", "code": "666666", "new_password": "audited-new-pw"},
    )

    conn = await raw_connection(db_session)
    # 기존 감사 테스트(test_core_audit.py)와 같은 raw SELECT 방식으로 마지막 행을 확인한다.
    action = await conn.fetchval(
        "SELECT action FROM audit_logs WHERE actor_id = $1 ORDER BY id DESC LIMIT 1", uid
    )
    assert action == AuditAction.PASSWORD_RESET
