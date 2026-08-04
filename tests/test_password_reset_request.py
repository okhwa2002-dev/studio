import re
from email import message_from_bytes
from email.policy import default as default_policy

import pytest

from app.config import get_settings
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


async def test_request_never_attempts_real_smtp_without_mail_env(client, db_session, monkeypatch):
    """mail_env를 받지 않은 테스트도 진짜 메일을 보내면 안 된다.

    SMTP를 끄는 장치가 옵트인이면, 로컬 .env에 SMTP가 설정된 개발자 머신에서 이
    엔드포인트를 때리는 테스트가 매번 실제 메일을 보낸다. 실제로 그렇게 새어나갔다 —
    스위트 한 번에 4통씩, 존재하지 않는 @example.com 주소로. 보호는 옵트인이 아니라
    기본값이어야 하고, 이 테스트가 그 기본값을 고정한다.

    발송 함수가 아니라 aiosmtplib.send를 감시하는 이유는 거기가 진짜 경계이기
    때문이다. send_email을 스텁하면 "실제로 나가지 않는다"가 아니라 "이 테스트가
    스텁했다"만 증명된다.
    """
    import aiosmtplib

    attempts = []

    async def _spy(*args, **kwargs):
        attempts.append(kwargs.get("hostname"))

    monkeypatch.setattr(aiosmtplib, "send", _spy)
    await _make_user(db_session, "no-real-mail@example.com")

    await client.post(
        "/api/auth/password-reset/request", json={"email": "no-real-mail@example.com"}
    )

    assert attempts == []


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


@pytest.fixture
def no_cooldown(monkeypatch):
    """재발송 쿨다운만 끈다.

    같은 이메일로 연달아 두 번 요청해야 하는 테스트가 쓴다. 그 테스트들이 검증하려는
    것은 코드 무효화이지 쿨다운이 아니므로, 쿨다운을 우회해 원래 의도를 살린다.
    """
    monkeypatch.setenv("RESET_REQUEST_COOLDOWN_SEC", "0")
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


async def test_request_invalidates_previous_code(client, db_session, no_cooldown):
    uid = await _make_user(db_session, "req-twice@example.com")
    conn = await raw_connection(db_session)

    await client.post("/api/auth/password-reset/request", json={"email": "req-twice@example.com"})
    first = await queries.find_active_reset_code(conn, user_id=uid)
    await client.post("/api/auth/password-reset/request", json={"email": "req-twice@example.com"})
    second = await queries.find_active_reset_code(conn, user_id=uid)

    # 활성 코드는 항상 최신 1개. 이전 코드는 무효화되어 최신 것과 다른 행이다.
    assert second["id"] != first["id"]


# ─── 요청 rate limit ───
#
# 엔드포인트 레벨에서는 "계정 존재를 흘리지 않는가"와 "IP를 어디서 읽는가"를 본다.
# 창·경계 자체의 검증은 tests/test_reset_rate_limit.py가 맡는다.


async def test_second_request_within_cooldown_returns_429(client, db_session, mail_env):
    await _make_user(db_session, "rl-active@example.com")

    first = await client.post(
        "/api/auth/password-reset/request", json={"email": "rl-active@example.com"}
    )
    second = await client.post(
        "/api/auth/password-reset/request", json={"email": "rl-active@example.com"}
    )

    assert first.status_code == 200
    assert second.status_code == 429
    assert second.json()["code"] == "TOO_MANY_RESET_REQUESTS"


async def test_unknown_email_is_rate_limited_too(client, db_session, mail_env):
    """가입도 안 한 주소를 제한하지 않으면 429가 곧 '계정 있음' 신호가 된다."""
    first = await client.post(
        "/api/auth/password-reset/request", json={"email": "rl-nobody@example.com"}
    )
    second = await client.post(
        "/api/auth/password-reset/request", json={"email": "rl-nobody@example.com"}
    )

    assert first.status_code == 200
    assert second.status_code == 429


async def test_429_is_identical_for_existing_and_missing_accounts(client, db_session, mail_env):
    await _make_user(db_session, "rl-there@example.com")

    for email in ("rl-there@example.com", "rl-not-there@example.com"):
        await client.post("/api/auth/password-reset/request", json={"email": email})

    blocked = [
        await client.post("/api/auth/password-reset/request", json={"email": email})
        for email in ("rl-there@example.com", "rl-not-there@example.com")
    ]

    assert blocked[0].status_code == blocked[1].status_code == 429
    assert blocked[0].json() == blocked[1].json()


async def test_rate_limited_request_sends_no_mail(client, db_session, mail_env):
    await _make_user(db_session, "rl-nomail@example.com")

    await client.post("/api/auth/password-reset/request", json={"email": "rl-nomail@example.com"})
    await client.post("/api/auth/password-reset/request", json={"email": "rl-nomail@example.com"})

    # 첫 요청의 1통뿐 — 거부된 요청은 메일을 만들지 않는다.
    assert len(list(mail_env.glob("*.eml"))) == 1


async def test_x_forwarded_for_is_ignored(client, db_session, mail_env):
    """헤더를 신뢰하면 값만 바꿔가며 IP 축을 통째로 우회할 수 있다.

    같은 이메일로 두 번 보내되 두 번째에 다른 X-Forwarded-For를 붙인다. 헤더를
    읽는다면 다른 출처로 보여 통과할 것이고, 무시한다면 쿨다운에 걸려 429가 된다.
    """
    await _make_user(db_session, "rl-xff@example.com")

    await client.post("/api/auth/password-reset/request", json={"email": "rl-xff@example.com"})
    second = await client.post(
        "/api/auth/password-reset/request",
        json={"email": "rl-xff@example.com"},
        headers={"X-Forwarded-For": "203.0.113.7"},
    )

    assert second.status_code == 429


async def test_uppercase_email_shares_the_same_bucket(client, db_session, mail_env):
    """정규화하지 않으면 대소문자만 바꿔 제한을 무한 우회할 수 있다."""
    await _make_user(db_session, "rl-case@example.com")

    await client.post("/api/auth/password-reset/request", json={"email": "rl-case@example.com"})
    second = await client.post(
        "/api/auth/password-reset/request", json={"email": "RL-Case@Example.com"}
    )

    assert second.status_code == 429


# ─── 인증코드 메일 발송 ───
#
# mail_env가 SMTP를 끄고 LOG_DIR을 tmp_path로 돌리므로, 발송은 .eml 파일 1개로 나타난다.
# conftest의 AsyncClient(ASGITransport)는 ASGI 호출이 끝날 때까지 기다리고 백그라운드
# 태스크는 그 안에서 실행되므로, await client.post(...)가 돌아온 시점에 파일이 이미 있다.


async def test_request_sends_the_code_by_email(client, db_session, mail_env):
    uid = await _make_user(db_session, "req-mail@example.com")

    await client.post("/api/auth/password-reset/request", json={"email": "req-mail@example.com"})

    files = list(mail_env.glob("*.eml"))
    assert len(files) == 1

    conn = await raw_connection(db_session)
    row = await queries.find_active_reset_code(conn, user_id=uid)
    # .eml 원문을 문자열로 훑지 않는다 — 본문이 한글이라 base64로 인코딩돼 있어
    # 코드가 평문으로 보이지 않는다. 파싱해서 디코딩된 본문을 본다.
    message = message_from_bytes(files[0].read_bytes(), policy=default_policy)
    # 메일에 담긴 코드가 DB에 저장된 바로 그 코드다.
    assert row["code"] in message.get_content()


async def test_request_unknown_email_sends_nothing(client, db_session, mail_env):
    await client.post("/api/auth/password-reset/request", json={"email": "nobody@example.com"})

    assert list(mail_env.glob("*.eml")) == []


async def test_request_disabled_account_sends_nothing(client, db_session, mail_env):
    await _make_user(db_session, "req-mail-disabled@example.com", status="DISABLED")

    await client.post(
        "/api/auth/password-reset/request", json={"email": "req-mail-disabled@example.com"}
    )

    assert list(mail_env.glob("*.eml")) == []
