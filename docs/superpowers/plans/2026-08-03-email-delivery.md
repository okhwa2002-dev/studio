# 이메일 발송 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** SMTP로 메일을 보내는 범용 발송기 `send_email()`을 만들고, 비밀번호 재설정 인증코드를 그것으로 실제 발송한다.

**Architecture:** 3계층이다. 라우터가 `BackgroundTasks`로 발송을 예약하고 → `deliver_reset_code()`가 재설정 메일의 제목·본문을 만들고 → `app/core/email.py`의 `send_email()`이 SMTP로 보낸다. `SMTP_HOST`가 비어 있으면 보내는 대신 `LOG_DIR/mail/*.eml` 파일로 저장한다(개발용 폴백). 발송기는 누가 왜 보내는지 모르고, 재설정 쪽은 어떻게 보내는지 모른다.

**Tech Stack:** Python 3.12 · FastAPI · aiosmtplib · 표준 라이브러리 `email.message.EmailMessage` · pytest (asyncio_mode=auto)

**설계 문서:** [docs/superpowers/specs/2026-08-03-email-delivery-design.md](../specs/2026-08-03-email-delivery-design.md)

## Global Constraints

- **인증코드를 로그에 남기지 않는다.** 메일 본문·코드는 어떤 `logger` 호출에도 들어가지 않는다. 실패 로그는 수신자·제목·예외만 남긴다.
- **발송 실패를 사용자에게 전파하지 않는다.** `deliver_reset_code()`가 예외를 삼킨다. "이 주소로는 발송이 실패했다"는 신호 자체가 계정 존재를 알려주기 때문이다(계정 열거 방지).
- **주석과 문서는 한국어로 쓴다.** 기존 코드베이스 전체가 한국어 주석이다. 주석은 "무엇을"이 아니라 "왜"를 적는다.
- **모든 API 경로는 `/api` 접두사 아래에 있다.** 재설정 요청은 `POST /api/auth/password-reset/request`.
- **의존성 추가:** `aiosmtplib>=3.0` (Task 2에서 `pyproject.toml`에 넣는다).
- **테스트 실행:** `pytest tests/<file> -v`. `asyncio_mode=auto`라 `async def test_...`에 데코레이터가 필요 없다.
- **`get_settings()`는 `lru_cache`다.** 테스트에서 env를 바꾸면 반드시 `get_settings.cache_clear()`를 부른다.
- **커밋은 기능 단위로 나눈다.** `git add .`을 쓰지 않고 파일을 이름으로 고른다(README 규칙).

---

## File Structure

| 파일 | 역할 | Task |
|---|---|---|
| `app/config.py` | `SMTP_*` 설정 7개 + `smtp_tls` 값 검증 | 1 |
| `.env.example` | 같은 7개를 주석과 함께 | 1 |
| `app/core/email.py` (신규) | `send_email()` — 메시지 조립, 파일 폴백, SMTP 발송 | 1, 2 |
| `tests/conftest.py` | `mail_env` 픽스처 (LOG_DIR→tmp_path, SMTP 끔) | 1 |
| `tests/test_email.py` (신규) | 발송기 단위 테스트 | 1, 2 |
| `pyproject.toml` | `aiosmtplib>=3.0` | 2 |
| `app/auth/password_reset.py` | `deliver_reset_code()` 몸통 — 제목·본문·예외 삼킴 | 3 |
| `tests/test_password_reset_deliver.py` (신규) | 재설정 메일 내용 테스트 | 3 |
| `app/auth/router.py` | 동기 호출 → `background.add_task` | 4 |
| `tests/test_password_reset_request.py` | 엔드포인트가 발송을 예약하는지 | 4 |
| `app/main.py` | 기동 시 SMTP 미설정 경고 | 5 |
| `README.md` | ⚠️ 경고 삭제 → SMTP 안내 | 5 |
| `docs/superpowers/specs/2026-07-31-password-reset-design.md` | §0 경고에 "해소됨" 표시 | 5 |

---

## Task 1: SMTP 설정 + 파일 폴백 발송기

**Files:**
- Modify: `app/config.py` (`Settings` 클래스에 필드 7개 + validator)
- Modify: `.env.example` (파일 끝에 추가)
- Create: `app/core/email.py`
- Modify: `tests/conftest.py` (`mail_env` 픽스처 추가)
- Test: `tests/test_email.py` (신규)

**Interfaces:**
- Consumes: `app.config.get_settings()`, `app.utils.time.now_local()`
- Produces:
  - `Settings.smtp_host/smtp_port/smtp_user/smtp_password/smtp_from/smtp_tls/smtp_timeout_sec`
  - `app.core.email.send_email(to: str, subject: str, body: str) -> None` (async, 반환 없음)
  - `app.core.email.MAIL_DIR_NAME = "mail"`
  - `tests/conftest.py`의 `mail_env` 픽스처 — `Path`(=`tmp_path/"mail"`)를 yield한다

---

- [ ] **Step 1: `Settings`에 SMTP 필드 7개와 validator를 추가한다**

`app/config.py`의 `stock_timeout_sec: int = 30` 줄 **바로 아래**에 넣는다:

```python
    # --- 이메일(SMTP) ---
    # SMTP_HOST가 비어 있으면 메일을 보내지 않고 LOG_DIR/mail/*.eml로 저장한다(개발용 폴백).
    # 이 키 하나가 모드 스위치다 — 운영에서 빠뜨리면 기동 로그에 경고가 남는다(app/main.py).
    smtp_host: str = ""
    smtp_port: int = 587
    # 인증 없는 사내 릴레이도 있으므로 빈 값을 허용한다(빈 값이면 인증을 시도하지 않는다).
    smtp_user: str = ""
    smtp_password: str = ""
    # 발신자. 비면 smtp_user를 쓴다. "Studio <no-reply@x.com>" 형식도 그대로 넣을 수 있어
    # 표시 이름을 위한 별도 키를 두지 않는다.
    smtp_from: str = ""
    # 셋 중 하나. 불리언 두 개(use_tls/use_starttls)로 쪼개면 "둘 다 참"처럼 성립할 수
    # 없는 조합이 표현된다.
    smtp_tls: str = "starttls"
    # 백그라운드로 돌더라도 무한정 매달리지 않게 한다.
    smtp_timeout_sec: int = 15
```

그리고 `_jwt_secret_at_least_32_bytes` validator **아래**에 추가한다:

```python
    @field_validator("smtp_tls")
    @classmethod
    def _known_smtp_tls(cls, value: str) -> str:
        allowed = ("starttls", "ssl", "none")
        if value not in allowed:
            raise ValueError(f"SMTP_TLS는 {' | '.join(allowed)} 중 하나여야 합니다: {value}")
        return value
```

- [ ] **Step 2: `mail_env` 픽스처를 conftest에 추가한다**

`tests/conftest.py` 맨 아래에 추가한다. `get_settings`는 파일 22번째 줄에서 이미 import돼 있다.

```python
@pytest.fixture
def mail_env(tmp_path, monkeypatch):
    """메일을 파일로 떨구는 개발 모드로 고정하고, 그 출력 디렉토리를 준다.

    LOG_DIR을 tmp_path로 돌려 테스트가 실제 log/ 디렉토리를 더럽히지 않게 하고,
    SMTP_HOST를 비워 로컬 .env에 SMTP 설정이 있어도 진짜 메일이 나가지 않게 한다.
    get_settings는 lru_cache라 env를 바꾼 뒤 캐시를 비워야 반영된다.
    """
    monkeypatch.setenv("LOG_DIR", str(tmp_path))
    monkeypatch.setenv("SMTP_HOST", "")
    # 발신자도 비워 둔다 — 로컬 .env에 SMTP_FROM이 있으면 폴백 테스트가 흔들린다.
    monkeypatch.setenv("SMTP_USER", "")
    monkeypatch.setenv("SMTP_FROM", "")
    get_settings.cache_clear()
    yield tmp_path / "mail"
    get_settings.cache_clear()
```

- [ ] **Step 3: 실패하는 테스트를 쓴다**

`tests/test_email.py`를 새로 만든다:

```python
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
```

- [ ] **Step 4: 테스트가 실패하는 것을 확인한다**

Run: `pytest tests/test_email.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.core.email'` (수집 단계에서 전부 에러)

- [ ] **Step 5: 발송기를 만든다 (파일 폴백만)**

`app/core/email.py`를 새로 만든다:

```python
import logging
import re
from email.message import EmailMessage
from pathlib import Path

from app.config import get_settings
from app.utils.time import now_local

logger = logging.getLogger(__name__)

# LOG_DIR 아래 이 이름의 디렉토리에 .eml을 떨군다.
MAIL_DIR_NAME = "mail"

# 파일명에 그대로 쓸 수 있는 문자만 남긴다.
_UNSAFE_FILENAME = re.compile(r"[^A-Za-z0-9._-]")


def _build_message(to: str, subject: str, body: str) -> EmailMessage:
    """메일 1통을 조립한다.

    헤더를 손으로 만들지 않는다 — EmailMessage가 본문 UTF-8 인코딩과 제목의
    RFC 2047 인코딩을 처리한다. 한글 제목을 직접 조립하면 클라이언트에 따라 깨진다.
    """
    settings = get_settings()
    message = EmailMessage()
    message["From"] = settings.smtp_from or settings.smtp_user
    message["To"] = to
    message["Subject"] = subject
    message.set_content(body)
    return message


def _eml_path(to: str) -> Path:
    """LOG_DIR/mail/{시각}_{수신자}.eml

    밀리초까지 넣는 이유는 같은 초에 두 통이 나가도 덮어쓰지 않게 하기 위함이다.
    """
    stamp = now_local().strftime("%Y%m%d-%H%M%S-%f")[:-3]
    safe = _UNSAFE_FILENAME.sub("_", to.replace("@", "_at_"))
    return Path(get_settings().log_dir) / MAIL_DIR_NAME / f"{stamp}_{safe}.eml"


def _save_to_file(message: EmailMessage) -> Path:
    path = _eml_path(message["To"])
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(bytes(message))
    return path


async def send_email(to: str, subject: str, body: str) -> None:
    """메일 1통을 보낸다.

    SMTP_HOST가 없으면 보내는 대신 LOG_DIR/mail/*.eml로 저장한다. 콘솔·서버 로그가
    아니라 파일인 이유는, 인증코드 같은 본문이 로그 수집기를 타고 나가지 않게 하기
    위함이다(log/는 .gitignore 대상이라 저장소에도 섞이지 않는다).

    이 함수는 누가 왜 보내는지 모른다 — 새 메일 종류가 생기면 이 위층에 함수를
    하나 더할 뿐 여기는 손대지 않는다.
    """
    message = _build_message(to, subject, body)
    path = _save_to_file(message)
    logger.info("SMTP 미설정 — 메일을 파일로 저장했습니다: %s", path)
```

- [ ] **Step 6: 테스트가 통과하는 것을 확인한다**

Run: `pytest tests/test_email.py -v`
Expected: PASS (8개)

- [ ] **Step 7: 기존 테스트가 깨지지 않았는지 확인한다**

Run: `pytest tests/test_password_reset_request.py tests/test_password_reset_confirm.py -v`
Expected: PASS — 이 단계에서는 `deliver_reset_code`가 아직 빈 함수라 동작이 그대로다.

- [ ] **Step 8: `.env.example`에 7개를 추가한다**

파일 맨 아래(`STOCK_TIMEOUT_SEC=30` 다음)에 붙인다:

```
# 이메일(SMTP) — 비밀번호 재설정 인증코드가 이 설정으로 발송된다.
# SMTP_HOST가 비어 있으면 메일을 보내지 않고 LOG_DIR/mail/*.eml 파일로 저장한다(개발용).
SMTP_HOST=
SMTP_PORT=587
# 인증이 필요 없는 릴레이면 USER/PASSWORD를 비워 둔다.
SMTP_USER=
SMTP_PASSWORD=
# 발신자. 비우면 SMTP_USER를 쓴다. "Studio <no-reply@example.com>" 형식도 된다.
SMTP_FROM=
# 허용: starttls(587) | ssl(465) | none(로컬 Mailpit 등). 다른 값이면 기동하지 않는다.
SMTP_TLS=starttls
# 발송 타임아웃(초).
SMTP_TIMEOUT_SEC=15
```

- [ ] **Step 9: 커밋**

```bash
git add app/config.py app/core/email.py tests/conftest.py tests/test_email.py .env.example
git commit -m "feat: 이메일 발송기 추가 (SMTP 미설정 시 .eml 파일 저장)"
```

---

## Task 2: SMTP 실제 발송 경로

**Files:**
- Modify: `pyproject.toml` (dependencies에 1줄)
- Modify: `app/core/email.py` (`_send_via_smtp` 추가 + `send_email` 분기)
- Test: `tests/test_email.py` (테스트 4개 추가)

**Interfaces:**
- Consumes: Task 1의 `send_email()`, `Settings.smtp_*`, `mail_env` 픽스처
- Produces: `app.core.email._send_via_smtp(message: EmailMessage) -> None` (async). 외부에서 부르지 않는다 — `send_email`이 유일한 공개 진입점이다.

---

- [ ] **Step 1: 의존성을 추가한다**

`pyproject.toml`의 `dependencies` 리스트에서 `"httpx>=0.28",` **다음 줄**에 넣는다:

```toml
    "aiosmtplib>=3.0",
```

그리고 설치한다:

Run: `uv sync`
(uv를 쓰지 않는 환경이면 `pip install "aiosmtplib>=3.0"`)

> 표준 라이브러리 `smtplib`를 쓰지 않는 이유: 블로킹이라 이벤트 루프를 멈춘다. 백그라운드 태스크도 같은 루프에서 돌기 때문에, 발송하는 몇 초 동안 다른 요청이 전부 대기한다. `aiosmtplib`는 같은 `EmailMessage` 객체를 그대로 받으므로 본문 조립 코드는 바뀌지 않는다.

- [ ] **Step 2: 실패하는 테스트를 쓴다**

`tests/test_email.py` 맨 아래에 추가한다:

```python
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
```

- [ ] **Step 3: 테스트가 실패하는 것을 확인한다**

Run: `pytest tests/test_email.py -v -k "smtp or tls or credentials"`
Expected: FAIL — SMTP가 설정돼 있어도 여전히 파일로 저장하므로 `assert len(sent) == 1`이 `0 == 1`로 깨진다.

- [ ] **Step 4: SMTP 분기를 구현한다**

`app/core/email.py` 맨 위 import에 한 줄 추가한다:

```python
import aiosmtplib
```

`_save_to_file` **아래**, `send_email` **위**에 추가한다:

```python
async def _send_via_smtp(message: EmailMessage) -> None:
    settings = get_settings()
    # 빈 문자열이 아니라 None을 넘긴다 — 빈 계정으로 AUTH를 시도하면 릴레이가 거절한다.
    await aiosmtplib.send(
        message,
        hostname=settings.smtp_host,
        port=settings.smtp_port,
        username=settings.smtp_user or None,
        password=settings.smtp_password or None,
        use_tls=settings.smtp_tls == "ssl",          # 465 — 접속부터 암호화
        start_tls=settings.smtp_tls == "starttls",   # 587 — 평문 접속 후 승격
        timeout=settings.smtp_timeout_sec,
    )
```

`send_email`의 몸통을 다음으로 교체한다(독스트링은 그대로 둔다):

```python
    message = _build_message(to, subject, body)
    if not get_settings().smtp_host:
        path = _save_to_file(message)
        logger.info("SMTP 미설정 — 메일을 파일로 저장했습니다: %s", path)
        return
    await _send_via_smtp(message)
```

- [ ] **Step 5: 테스트가 통과하는 것을 확인한다**

Run: `pytest tests/test_email.py -v`
Expected: PASS (14개 — Task 1의 8개 + 새 6개)

- [ ] **Step 6: 커밋**

```bash
git add pyproject.toml app/core/email.py tests/test_email.py
git commit -m "feat: SMTP 발송 경로 추가 (starttls/ssl/none)"
```

---

## Task 3: 재설정 인증코드 메일

**Files:**
- Modify: `app/auth/password_reset.py:16-31` (`deliver_reset_code` 몸통을 채운다)
- Test: `tests/test_password_reset_deliver.py` (신규)

**Interfaces:**
- Consumes: `app.core.email.send_email(to, subject, body)` (Task 1·2), 기존 상수 `RESET_CODE_TTL_MINUTES = 10`
- Produces: `app.auth.password_reset.deliver_reset_code(email: str, code: str) -> None` — **`async def`로 바뀐다**(Task 4가 이 사실에 의존한다). 예외를 던지지 않는다.
- 순환 import 없음: `app.core.email`은 `app.config`·`app.utils.time`만 import한다.

---

- [ ] **Step 1: 실패하는 테스트를 쓴다**

`tests/test_password_reset_deliver.py`를 새로 만든다:

```python
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
```

- [ ] **Step 2: 테스트가 실패하는 것을 확인한다**

Run: `pytest tests/test_password_reset_deliver.py -v`
Expected: FAIL — `AttributeError: <module 'app.auth.password_reset'> has no attribute 'send_email'` (아직 import하지 않았다)

- [ ] **Step 3: `deliver_reset_code`를 구현한다**

`app/auth/password_reset.py`의 맨 위 import를 다음으로 바꾼다:

```python
import logging
import secrets

from app.core.email import send_email

logger = logging.getLogger(__name__)

RESET_CODE_TTL_MINUTES = 10
MAX_RESET_ATTEMPTS = 5
```

그리고 파일 끝의 `deliver_reset_code` **전체**(16~31행)를 다음으로 교체한다:

```python
_RESET_SUBJECT = "[Studio] 비밀번호 재설정 인증코드"


async def deliver_reset_code(email: str, code: str) -> None:
    """생성된 코드를 사용자에게 이메일로 전달한다 — 이 기능의 유일한 전달 경계다.

    라우터가 이 함수를 BackgroundTasks로 예약한다(응답 이후에 실행된다). 동기로
    부르면 가입된 이메일일 때만 응답이 수 초 느려져, 응답 본문을 통일해 막아 둔
    계정 열거가 응답 시간으로 새어나간다.

    발송 실패는 삼킨다. 응답은 이미 나갔고, 실패를 알릴 방법이 있더라도 그 신호가
    곧 계정 존재를 알려준다. 실패한 코드는 10분 뒤 만료되고 정리 잡이 지우며,
    사용자가 다시 요청하면 새 코드가 나가므로 재시도할 이유도 없다.

    로그에 코드·본문을 남기지 않는다 — 수신자·예외만 남긴다.
    """
    body = (
        f"인증코드: {code}\n"
        "\n"
        f"이 코드는 {RESET_CODE_TTL_MINUTES}분 뒤에 만료됩니다.\n"
        "본인이 요청하지 않았다면 이 메일을 무시하세요.\n"
    )
    try:
        await send_email(to=email, subject=_RESET_SUBJECT, body=body)
    except Exception:
        logger.warning("비밀번호 재설정 메일 발송 실패: to=%s", email, exc_info=True)
```

> `generate_reset_code()`는 그대로 둔다.

- [ ] **Step 4: 테스트가 통과하는 것을 확인한다**

Run: `pytest tests/test_password_reset_deliver.py -v`
Expected: PASS (7개)

- [ ] **Step 5: 커밋**

```bash
git add app/auth/password_reset.py tests/test_password_reset_deliver.py
git commit -m "feat: 비밀번호 재설정 인증코드 메일 발송"
```

---

## Task 4: 라우터가 발송을 백그라운드로 예약한다

**Files:**
- Modify: `app/auth/router.py:4` (import), `app/auth/router.py:424-448` (엔드포인트)
- Test: `tests/test_password_reset_request.py` (테스트 3개 추가)

**Interfaces:**
- Consumes: `deliver_reset_code(email, code)` — Task 3에서 `async def`가 됐다. `BackgroundTasks.add_task`는 async 함수를 그대로 받는다.
- Produces: 엔드포인트 동작 변화 없음(응답 본문·상태 코드 동일). 발송이 응답 이후로 옮겨질 뿐이다.

---

- [ ] **Step 1: 실패하는 테스트를 쓴다**

먼저 `tests/test_password_reset_request.py` 맨 위 `import re` 아래에 두 줄을 더한다:

```python
from email import message_from_bytes
from email.policy import default as default_policy
```

그리고 파일 맨 아래에 추가한다:

```python
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
```

- [ ] **Step 2: 테스트가 실패하는 것을 확인한다**

Run: `pytest tests/test_password_reset_request.py -v -k mail`
Expected: FAIL — `test_request_sends_the_code_by_email`이 `0 == 1`로 깨진다. 라우터가 `deliver_reset_code`를 **동기로** 부르는데 이제 그것이 코루틴이라, 호출은 아무 일도 하지 않고 "coroutine was never awaited" 경고만 남긴다.

- [ ] **Step 3: 라우터를 고친다**

`app/auth/router.py` 4번째 줄의 fastapi import에 `BackgroundTasks`를 더한다:

```python
from fastapi import APIRouter, BackgroundTasks, Depends, Request, Response
```

`password_reset_request`의 시그니처를 바꾼다(424~425행):

```python
@router.post("/password-reset/request")
async def password_reset_request(
    body: PasswordResetRequest,
    background: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
):
```

> `BackgroundTasks`는 기본값이 없으므로 `db=Depends(...)` **앞**에 와야 한다.

그리고 448행의 호출을 예약으로 바꾼다:

```python
        await db.commit()
        # 커밋 이후에 예약한다 — 저장이 롤백됐는데 코드만 나가는 일이 없도록.
        # 응답 이후에 실행되므로 SMTP 지연이 응답 시간에 섞이지 않는다. 동기로 보내면
        # 가입된 이메일일 때만 느려져, 통일한 응답 본문으로 막아 둔 계정 열거가
        # 응답 시간으로 새어나간다.
        background.add_task(deliver_reset_code, email, code)
```

- [ ] **Step 4: 테스트가 통과하는 것을 확인한다**

Run: `pytest tests/test_password_reset_request.py -v`
Expected: PASS (8개 — 기존 5개 + 새 3개)

- [ ] **Step 5: 재설정 관련 테스트 전체를 돌린다**

Run: `pytest tests/test_password_reset_request.py tests/test_password_reset_verify.py tests/test_password_reset_confirm.py tests/test_password_reset_code_model.py tests/test_password_reset_deliver.py tests/test_email.py tests/test_core_cleanup.py -v`
Expected: 전부 PASS

- [ ] **Step 6: 커밋**

```bash
git add app/auth/router.py tests/test_password_reset_request.py
git commit -m "feat: 인증코드 메일을 백그라운드로 발송"
```

---

## Task 5: 기동 경고와 문서 갱신

**Files:**
- Modify: `app/main.py` (import 1줄 + lifespan 안에 경고)
- Modify: `README.md:159-173` (`### 비밀번호 재설정` 절)
- Modify: `docs/superpowers/specs/2026-07-31-password-reset-design.md:8-16` (§0 경고에 해소 표시)

**Interfaces:**
- Consumes: `Settings.smtp_host`, `Settings.log_dir` (Task 1)
- Produces: 없음 (동작 변화 없는 마무리 작업)

---

- [ ] **Step 1: 기동 경고를 추가한다**

`app/main.py`의 **23행(`from app.auth.router import ...`)과 24행(`from app.core.cleanup import ...`) 사이**에 넣는다 — 기존 import가 알파벳 순이고 `app.config` < `app.core`다:

```python
from app.config import get_settings
```

`lifespan` 안에서 `check_env_defaults()` try 블록 **다음**, `worker = get_worker()` **앞**에 넣는다:

```python
    # 운영에서 SMTP_HOST를 빠뜨리면 메일이 조용히 파일로 간다. 기동을 막지는 않는다 —
    # 개발 환경에서는 그것이 정상 경로다. 대신 그 상태를 기동 로그에 드러낸다.
    if not get_settings().smtp_host:
        logger.warning(
            "SMTP_HOST가 없어 메일을 보내지 않고 파일로 저장합니다: %s/mail",
            get_settings().log_dir,
        )
```

- [ ] **Step 2: 앱이 기동하는지 확인한다**

Run: `pytest tests/test_health.py -v`
Expected: PASS

- [ ] **Step 3: README를 고친다**

`README.md`의 `### 비밀번호 재설정` 절(159행부터)에서 **⚠️ 경고 블록(163행) 전체를 삭제**하고, 그 자리에 다음을 넣는다:

```markdown
인증코드는 `.env`의 `SMTP_*` 설정으로 발송된다(`SMTP_HOST`·`SMTP_PORT`·`SMTP_USER`·`SMTP_PASSWORD`·`SMTP_FROM`·`SMTP_TLS`·`SMTP_TIMEOUT_SEC` — 값 설명은 `.env.example` 참고). 발송은 응답을 보낸 뒤 백그라운드로 이뤄진다 — 동기로 보내면 가입된 주소일 때만 응답이 느려져 계정 존재가 드러난다.

**`SMTP_HOST`가 비어 있으면 메일을 보내지 않고 `LOG_DIR/mail/*.eml` 파일로 저장한다.** 개발 중에는 이 파일을 열어 인증코드를 확인한다(Outlook·Thunderbird·VS Code에서 바로 열린다). 기동 시 로그에 이 상태가 경고로 남으므로, 운영에서 설정을 빠뜨렸는지 로그로 알 수 있다.

발송이 실패하면 사용자에게는 알리지 않고(계정 존재를 드러내지 않기 위해) 서버 로그에만 남는다. 이때는 테이블에서 코드를 직접 확인한다.
```

기존의 SQL 블록(167~171행)과 정리 잡 문장(173행)은 **그대로 둔다** — 발송이 실패했을 때 코드를 확인하는 마지막 수단으로 여전히 유효하다.

- [ ] **Step 4: 기존 설계 문서에 해소 표시를 남긴다**

`docs/superpowers/specs/2026-07-31-password-reset-design.md`의 `## 0. 보안 경고` 제목 **바로 아래**(9행, 인용 블록 앞)에 한 줄 추가한다:

```markdown
> ✅ **해소됨 (2026-08-03)** — `deliver_reset_code()`가 실제 이메일 발송으로 채워졌다. 아래 경고는 히스토리로 남긴다. [이메일 발송 설계](2026-08-03-email-delivery-design.md) 참고.
```

본문은 지우지 않는다. 지우면 왜 이 이음새가 이렇게 생겼는지가 사라진다.

- [ ] **Step 5: 전체 테스트를 돌린다**

Run: `pytest -v`
Expected: 전부 PASS (`-m "not slow"` 없이 전부 — 기존 규칙)

> 전체 실행에는 Docker가 필요하다 — `conftest.py`가 `testcontainers`로 Postgres 16 컨테이너를 띄운다. Docker가 없으면 DB를 쓰지 않는 `tests/test_email.py`·`tests/test_password_reset_deliver.py`만 돌려도 이 작업의 새 코드는 전부 검증된다.

- [ ] **Step 6: 커밋**

```bash
git add app/main.py
git commit -m "feat: SMTP 미설정 시 기동 로그에 경고"

git add README.md docs/superpowers/specs/2026-07-31-password-reset-design.md
git commit -m "docs: 이메일 발송 설정 안내로 재설정 경고 대체"
```

---

## 수동 검증 (전체 완료 후)

- [ ] `SMTP_HOST`를 비운 채 앱을 띄우고 기동 로그에 경고가 찍히는지 본다.
- [ ] 로그인 화면 → "비밀번호를 잊으셨나요?" → 실재 이메일 입력.
- [ ] `log/studio/mail/`에 `.eml`이 생겼는지 확인하고 열어 본다 — 제목·본문 한글이 깨지지 않고 6자리 코드가 보여야 한다.
- [ ] 그 코드로 2단계·3단계를 통과해 비밀번호가 바뀌는지 확인한다.
- [ ] (SMTP 계정이 있다면) `.env`에 `SMTP_HOST`·`SMTP_USER`·`SMTP_PASSWORD`·`SMTP_FROM`을 넣고 재시작해 실제 메일함으로 코드가 오는지 확인한다.
