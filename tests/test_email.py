from email import message_from_bytes
from email.policy import default as default_policy

import pytest
from pydantic import ValidationError

from app.config import get_settings
from app.core.email import send_email


def _read_eml(path):
    """저장된 .eml을 다시 파싱한다. policy=default라야 제목의 RFC 2047 인코딩이 풀린다."""
    return message_from_bytes(path.read_bytes(), policy=default_policy)


async def test_saves_eml_when_smtp_not_configured(mail_env):
    await send_email(to="dev@example.com", subject="제목", body="본문")

    files = list(mail_env.glob("*.eml"))
    assert len(files) == 1


async def test_eml_contains_recipient_subject_and_body(mail_env):
    await send_email(to="dev@example.com", subject="제목", body="본문 한 줄")

    message = _read_eml(next(mail_env.glob("*.eml")))
    assert message["To"] == "dev@example.com"
    assert message["Subject"] == "제목"
    # set_content()는 본문 끝에 개행을 붙인다.
    assert message.get_content().rstrip("\n") == "본문 한 줄"


async def test_korean_multiline_body_round_trips(mail_env):
    body = "인증코드: 042917\n\n이 코드는 10분 뒤에 만료됩니다.\n"
    await send_email(to="dev@example.com", subject="[Studio] 비밀번호 재설정 인증코드", body=body)

    message = _read_eml(next(mail_env.glob("*.eml")))
    assert message["Subject"] == "[Studio] 비밀번호 재설정 인증코드"
    assert message.get_content() == body


async def test_two_mails_to_same_address_do_not_overwrite(mail_env):
    await send_email(to="dev@example.com", subject="첫째", body="1")
    await send_email(to="dev@example.com", subject="둘째", body="2")

    assert len(list(mail_env.glob("*.eml"))) == 2


async def test_filename_has_no_at_sign(mail_env):
    # @는 경로에 넣기 껄끄러운 문자라 _at_으로 바꾼다.
    await send_email(to="dev@example.com", subject="제목", body="본문")

    name = next(mail_env.glob("*.eml")).name
    assert "@" not in name
    assert "_at_" in name


async def test_from_falls_back_to_smtp_user(mail_env, monkeypatch):
    monkeypatch.setenv("SMTP_USER", "no-reply@example.com")
    get_settings.cache_clear()

    await send_email(to="dev@example.com", subject="제목", body="본문")

    message = _read_eml(next(mail_env.glob("*.eml")))
    assert message["From"] == "no-reply@example.com"


async def test_smtp_from_wins_over_smtp_user(mail_env, monkeypatch):
    monkeypatch.setenv("SMTP_USER", "login@example.com")
    monkeypatch.setenv("SMTP_FROM", "Studio <no-reply@example.com>")
    get_settings.cache_clear()

    await send_email(to="dev@example.com", subject="제목", body="본문")

    message = _read_eml(next(mail_env.glob("*.eml")))
    assert "no-reply@example.com" in message["From"]


def test_invalid_smtp_tls_is_rejected(monkeypatch):
    # 오타가 조용히 "암호화 없음"이 되지 않게 기동 시점에 막는다.
    monkeypatch.setenv("SMTP_TLS", "tls")
    get_settings.cache_clear()
    try:
        with pytest.raises(ValidationError):
            get_settings()
    finally:
        monkeypatch.delenv("SMTP_TLS", raising=False)
        get_settings.cache_clear()


# ─── SMTP 발송 경로 ───


@pytest.fixture
def sent(monkeypatch, tmp_path):
    """aiosmtplib.send를 가로채 호출 인자를 담아 준다. 실제 접속은 하지 않는다."""
    import aiosmtplib

    calls = []

    async def _fake_send(message, **kwargs):
        calls.append({"message": message, **kwargs})

    monkeypatch.setattr(aiosmtplib, "send", _fake_send)
    monkeypatch.setenv("LOG_DIR", str(tmp_path))
    monkeypatch.setenv("SMTP_HOST", "smtp.example.com")
    monkeypatch.setenv("SMTP_PORT", "587")
    monkeypatch.setenv("SMTP_USER", "login@example.com")
    monkeypatch.setenv("SMTP_PASSWORD", "secret")
    monkeypatch.setenv("SMTP_TIMEOUT_SEC", "9")
    # 로컬 .env 값에 흔들리지 않게 나머지도 못박는다.
    monkeypatch.setenv("SMTP_FROM", "")
    monkeypatch.setenv("SMTP_TLS", "starttls")
    get_settings.cache_clear()
    yield calls
    get_settings.cache_clear()


async def test_smtp_configured_sends_instead_of_writing_file(sent, tmp_path):
    await send_email(to="dev@example.com", subject="제목", body="본문")

    assert len(sent) == 1
    # 발송 모드에서는 파일을 남기지 않는다.
    assert not (tmp_path / "mail").exists()


async def test_smtp_connection_arguments(sent):
    await send_email(to="dev@example.com", subject="제목", body="본문")

    call = sent[0]
    assert call["hostname"] == "smtp.example.com"
    assert call["port"] == 587
    assert call["username"] == "login@example.com"
    assert call["password"] == "secret"
    assert call["timeout"] == 9
    assert call["message"]["To"] == "dev@example.com"


async def test_starttls_mode_flags(sent, monkeypatch):
    monkeypatch.setenv("SMTP_TLS", "starttls")
    get_settings.cache_clear()

    await send_email(to="dev@example.com", subject="제목", body="본문")

    assert sent[0]["use_tls"] is False
    assert sent[0]["start_tls"] is True


async def test_ssl_mode_flags(sent, monkeypatch):
    monkeypatch.setenv("SMTP_TLS", "ssl")
    get_settings.cache_clear()

    await send_email(to="dev@example.com", subject="제목", body="본문")

    assert sent[0]["use_tls"] is True
    assert sent[0]["start_tls"] is False


async def test_none_mode_disables_both(sent, monkeypatch):
    # 로컬 Mailpit처럼 암호화 없는 릴레이. start_tls를 None으로 두면 aiosmtplib이
    # 기회적으로 STARTTLS를 시도하므로 명시적으로 False를 넘긴다.
    monkeypatch.setenv("SMTP_TLS", "none")
    get_settings.cache_clear()

    await send_email(to="dev@example.com", subject="제목", body="본문")

    assert sent[0]["use_tls"] is False
    assert sent[0]["start_tls"] is False


async def test_empty_credentials_become_none(sent, monkeypatch):
    # 빈 문자열을 그대로 넘기면 aiosmtplib이 빈 계정으로 AUTH를 시도한다.
    monkeypatch.setenv("SMTP_USER", "")
    monkeypatch.setenv("SMTP_PASSWORD", "")
    get_settings.cache_clear()

    await send_email(to="dev@example.com", subject="제목", body="본문")

    assert sent[0]["username"] is None
    assert sent[0]["password"] is None
