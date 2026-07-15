import app.auth.router as auth_router
from app.auth.security import hash_password
from app.constants import UserStatus
from app.models.user import User


async def _create_user(db_session, email: str, password: str, status: str = UserStatus.ACTIVE) -> User:
    user = User(email=email, password_hash=hash_password(password), status=status)
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    return user


async def test_login_succeeds_for_active_user(client, db_session):
    await _create_user(db_session, "active@example.com", "pw12345")

    resp = await client.post(
        "/api/auth/login", json={"email": "active@example.com", "password": "pw12345"}
    )
    assert resp.status_code == 200
    assert resp.json()["email"] == "active@example.com"
    assert "access_token" in resp.cookies
    assert "refresh_token" in resp.cookies


async def test_login_rejects_wrong_password(client, db_session):
    await _create_user(db_session, "active2@example.com", "pw12345")

    resp = await client.post(
        "/api/auth/login", json={"email": "active2@example.com", "password": "wrong-pw"}
    )
    assert resp.status_code == 401


async def test_login_rejects_unknown_email(client):
    resp = await client.post(
        "/api/auth/login", json={"email": "nobody@example.com", "password": "pw12345"}
    )
    assert resp.status_code == 401


async def test_login_rejects_pending_user(client, db_session):
    await _create_user(db_session, "pending@example.com", "pw12345", status=UserStatus.PENDING)

    resp = await client.post(
        "/api/auth/login", json={"email": "pending@example.com", "password": "pw12345"}
    )
    assert resp.status_code == 403


async def test_login_succeeds_with_email_differing_in_case_and_whitespace(client, db_session):
    """등록 시 정규화(strip/lower)된 이메일이 저장되므로, 로그인도 동일하게
    정규화한 뒤 조회해야 대소문자/공백이 다른 이메일 입력으로도 로그인할 수 있다.
    """
    await _create_user(db_session, "casetest@example.com", "pw12345")

    resp = await client.post(
        "/api/auth/login",
        json={"email": "  CaseTest@Example.com  ", "password": "pw12345"},
    )
    assert resp.status_code == 200
    assert resp.json()["email"] == "casetest@example.com"


async def test_login_unknown_email_still_runs_password_verification(client, monkeypatch):
    """타이밍 사이드채널 회귀 테스트.

    `row is None or not verify_password(...)`처럼 단축 평가로 되돌리면
    이메일이 존재하지 않을 때 verify_password가 호출되지 않아, 응답 시간
    차이로 이메일 등록 여부를 추측할 수 있게 된다. 이 테스트는 실제 소요
    시간을 재는 대신(CI에서 불안정), 존재하지 않는 이메일로 로그인해도
    verify_password가 반드시 호출되는지를 검증한다.
    """
    calls = []
    original_verify_password = auth_router.verify_password

    def spy_verify_password(password, password_hash):
        calls.append((password, password_hash))
        return original_verify_password(password, password_hash)

    monkeypatch.setattr(auth_router, "verify_password", spy_verify_password)

    resp = await client.post(
        "/api/auth/login", json={"email": "definitely-does-not-exist@example.com", "password": "whatever"}
    )
    assert resp.status_code == 401
    assert len(calls) == 1
    assert calls[0][1] == auth_router._DUMMY_PASSWORD_HASH
