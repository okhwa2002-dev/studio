from datetime import timedelta

from app.db import raw_connection
from app.models.user import User
from app.queries import queries
from app.utils.time import now_local

_FAIL = "코드가 올바르지 않거나 만료되었습니다."
_VERIFY = "/api/auth/password-reset/verify"
_CONFIRM = "/api/auth/password-reset/confirm"


async def _user_with_code(db_session, email, code="123456", *, expired=False):
    user = User(email=email, password_hash="old-hash", name="테스트", role="MEMBER", status="ACTIVE")
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)

    conn = await raw_connection(db_session)
    now = now_local()
    expires = now - timedelta(minutes=1) if expired else now + timedelta(minutes=10)
    await queries.insert_reset_code(
        conn, user_id=user.id, code=code, expires_at=expires, created_at=now, updated_at=now
    )
    await db_session.commit()
    return user.id


async def test_verify_correct_code_does_not_consume_or_change_password(client, db_session):
    uid = await _user_with_code(db_session, "verify-ok@example.com", code="654321")

    resp = await client.post(_VERIFY, json={"email": "verify-ok@example.com", "code": "654321"})
    assert resp.status_code == 200

    conn = await raw_connection(db_session)
    # 검증만 했을 뿐 코드는 아직 살아 있고(소비 안 됨), 시도도 늘지 않는다.
    row = await queries.find_active_reset_code(conn, user_id=uid)
    assert row is not None
    assert row["attempts"] == 0
    # 비밀번호도 그대로다.
    assert (await queries.find_by_id(conn, id=uid))["password_hash"] == "old-hash"


async def test_verify_wrong_code_uniform_error_and_increments_attempts(client, db_session):
    uid = await _user_with_code(db_session, "verify-wrong@example.com", code="222222")

    resp = await client.post(_VERIFY, json={"email": "verify-wrong@example.com", "code": "000000"})
    assert resp.status_code == 400
    assert resp.json()["code"] == "INVALID_RESET_CODE"
    assert resp.json()["message"] == _FAIL

    conn = await raw_connection(db_session)
    assert (await queries.find_active_reset_code(conn, user_id=uid))["attempts"] == 1


async def test_verify_expired_code_uniform_error(client, db_session):
    await _user_with_code(db_session, "verify-exp@example.com", code="333333", expired=True)

    resp = await client.post(_VERIFY, json={"email": "verify-exp@example.com", "code": "333333"})
    assert resp.status_code == 400
    assert resp.json()["message"] == _FAIL


async def test_verify_unknown_email_uniform_error(client, db_session):
    resp = await client.post(_VERIFY, json={"email": "ghost@example.com", "code": "123456"})
    assert resp.status_code == 400
    assert resp.json()["message"] == _FAIL


async def test_verify_then_confirm_with_same_code_changes_password(client, db_session):
    uid = await _user_with_code(db_session, "verify-flow@example.com", code="777777")

    # 1) 코드 확인 단계
    v = await client.post(_VERIFY, json={"email": "verify-flow@example.com", "code": "777777"})
    assert v.status_code == 200

    # 2) 같은 코드로 비밀번호 변경 단계
    c = await client.post(
        _CONFIRM,
        json={"email": "verify-flow@example.com", "code": "777777", "new_password": "brand-new-pw"},
    )
    assert c.status_code == 200

    conn = await raw_connection(db_session)
    from app.auth.security import verify_password

    assert verify_password("brand-new-pw", (await queries.find_by_id(conn, id=uid))["password_hash"])
    assert await queries.find_active_reset_code(conn, user_id=uid) is None
