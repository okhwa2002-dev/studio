import pytest

from app.auth import password_reset
from app.auth.password_reset import RESET_CODE_TTL_MINUTES, deliver_reset_code


@pytest.fixture
def captured(monkeypatch):
    """send_email 호출을 가로챈다. password_reset이 이름으로 import했으므로 그쪽을 바꾼다."""
    calls = []

    async def _fake_send_email(to, subject, body):
        calls.append({"to": to, "subject": subject, "body": body})

    monkeypatch.setattr(password_reset, "send_email", _fake_send_email)
    return calls


async def test_sends_to_the_requested_address(captured):
    await deliver_reset_code("user@example.com", "042917")

    assert len(captured) == 1
    assert captured[0]["to"] == "user@example.com"


async def test_subject_is_fixed(captured):
    await deliver_reset_code("user@example.com", "042917")

    assert captured[0]["subject"] == "[Studio] 비밀번호 재설정 인증코드"


async def test_body_contains_the_code_with_leading_zero(captured):
    # 코드는 문자열이라 앞자리 0이 보존된다 — 본문에도 그대로 나가야 한다.
    await deliver_reset_code("user@example.com", "042917")

    assert "042917" in captured[0]["body"]


async def test_body_ttl_follows_the_constant(captured):
    await deliver_reset_code("user@example.com", "042917")

    assert f"{RESET_CODE_TTL_MINUTES}분" in captured[0]["body"]


async def test_body_warns_unrequested_recipients(captured):
    await deliver_reset_code("user@example.com", "042917")

    assert "본인이 요청하지 않았다면" in captured[0]["body"]


async def test_send_failure_is_swallowed(monkeypatch):
    """발송 실패는 호출자에게 전파되지 않는다.

    라우터가 이 함수를 백그라운드로 예약하므로 응답은 이미 나간 뒤다. 설령 전파할 수
    있어도 "이 주소로는 발송이 실패했다"는 신호 자체가 계정 존재를 알려준다.
    """

    async def _boom(to, subject, body):
        raise RuntimeError("SMTP 연결 실패")

    monkeypatch.setattr(password_reset, "send_email", _boom)

    await deliver_reset_code("user@example.com", "042917")  # 예외가 나지 않아야 한다


async def test_failure_log_does_not_leak_the_code(monkeypatch, caplog):
    async def _boom(to, subject, body):
        raise RuntimeError("SMTP 연결 실패")

    monkeypatch.setattr(password_reset, "send_email", _boom)

    with caplog.at_level("WARNING"):
        await deliver_reset_code("user@example.com", "042917")

    assert "042917" not in caplog.text
