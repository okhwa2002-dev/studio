# 재설정 요청 rate limit Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 비밀번호 재설정 요청을 이메일별·IP별로 제한해, 실제 메일 발송이 붙은 뒤 생긴 메일 폭탄·발신 한도 소진·재설정 봉쇄를 막는다.

**Architecture:** 새 테이블 `password_reset_requests`가 요청 원장이다. `check_and_record()`가 쿼리 한 번으로 세 축(쿨다운·이메일 시간당·IP 시간당)을 보고, 넘으면 429를 던지고 아니면 이번 요청을 기록한다. 라우터는 **계정을 조회하기 전에** 이 함수를 부른다 — 그래야 429가 계정 존재를 알려주지 않는다. 오래된 행은 기존 정리 잡이 지운다.

**Tech Stack:** Python 3.12 · FastAPI · SQLModel · asyncpg · aiosql · Alembic · pytest (asyncio_mode=auto)

**설계 문서:** [docs/superpowers/specs/2026-08-03-reset-rate-limit-design.md](../specs/2026-08-03-reset-rate-limit-design.md)

## Global Constraints

- **판정은 계정 조회보다 반드시 앞이다.** 발송이 일어날 때만 제한하면 `429 = 계정 있음`이 되어 계정 열거 방지가 깨진다.
- **거부된 요청은 기록하지 않는다.** 기록하면 공격자가 때리는 동안 창이 계속 밀려 피해자가 영원히 재설정하지 못한다.
- **이메일은 정규화(`strip().lower()`) 후 저장·조회한다.** 아니면 대소문자만 바꿔 제한을 무한 우회할 수 있다.
- **IP는 `request.client.host`만 쓴다. `X-Forwarded-For`를 읽지 않는다.** 프록시가 없는 배포에서 그 헤더를 신뢰하면 헤더 한 줄로 IP 축이 무력화된다([app/core/audit.py](../../../app/core/audit.py)의 방침과 동일).
- **판정 경계는 셋 다 `>=`다.** `email_window >= 5`면 6번째를 거부한다. 설정값은 "1시간에 허용하는 최대 통과 횟수"다.
- **429 응답은 어느 축에 걸렸는지 구분하지 않는다.** 코드·메시지는 항상 `TOO_MANY_RESET_REQUESTS` / `"요청이 너무 잦습니다. 잠시 후 다시 시도해 주세요."`.
- **주석과 문서는 한국어로 쓴다.** 주석은 "무엇을"이 아니라 "왜"를 적는다.
- **모든 API 경로는 `/api` 아래다.** 재설정 요청은 `POST /api/auth/password-reset/request`.
- **테스트 실행:** `.venv/Scripts/python.exe -m pytest tests/<file> -v`. `asyncio_mode=auto`라 `async def test_...`에 데코레이터가 필요 없다. DB를 쓰는 테스트는 Docker(testcontainers Postgres 16)가 필요하다.
- **테스트는 마이그레이션을 타지 않는다.** `tests/conftest.py`가 `SQLModel.metadata.create_all`로 테이블을 만든다. **테스트가 통과해도 Alembic 리비전은 따로 만들어야 한다** — 실배포는 그 경로로만 테이블이 생긴다.
- **커밋은 기능 단위로 나눈다.** `git add .`을 쓰지 않고 파일을 이름으로 고른다(README 규칙).

## 설계 문서에서 달라진 점 (1건)

설계 §2.2의 판정 쿼리를 **인덱스를 탈 수 있는 형태로 바꾼다.** 결과는 완전히 동일하다.

```sql
-- 설계 문서 원안: 바깥 WHERE가 created_at 뿐이라 seq scan이 된다
FROM password_reset_requests WHERE created_at > :window_since;

-- 이 계획: 바깥 WHERE로 email/client_ip 인덱스를 타게 좁힌다
FROM password_reset_requests
WHERE (email = :email OR client_ip = :client_ip) AND created_at > :window_since;
```

바깥에서 이미 `created_at > :window_since`로 걸러지므로 `email_window`·`ip_window` FILTER에서는 `created_at` 조건을 반복하지 않는다(쿨다운만 더 좁은 창이라 한 번 더 건다). 집합이 같음은 `cooldown_since >= window_since`가 항상 성립하기 때문이다.

그 결과 **`created_at` 인덱스가 판정 경로에 필요 없어진다.** 설계 §2.8이 그 인덱스를 두려던 이유가 판정 성능이었으므로, 인덱스는 `email`·`client_ip` 둘만 둔다. 정리 잡의 `DELETE ... WHERE created_at < :cutoff`는 하루 한 번 도는 작업이라 스캔해도 무방하다.

---

## File Structure

| 파일 | 역할 | Task |
|---|---|---|
| `app/models/password_reset_request.py` (신규) | 테이블 정의 | 1 |
| `app/models/__init__.py` | 모델 등록 | 1 |
| `alembic/versions/<신규>.py` | 실배포용 마이그레이션 | 1 |
| `docs/schema.sql` | 스키마 문서 | 1 |
| `tests/test_password_reset_request_model.py` (신규) | 컬럼·기본값·인덱스 | 1 |
| `app/config.py` | 한도 설정 3개 | 2 |
| `.env.example` | 같은 3개 + 주석 | 2 |
| `app/queries/password_reset_requests.sql` (신규) | `insert` · `count` | 2 |
| `app/auth/reset_rate_limit.py` (신규) | `check_and_record()` — 판정과 기록 | 2 |
| `tests/test_reset_rate_limit.py` (신규) | 판정 단위 테스트 | 2 |
| `app/auth/router.py` | 엔드포인트가 판정을 부른다 | 3 |
| `tests/test_password_reset_request.py` | 엔드포인트 레벨 검증 | 3 |
| `app/queries/password_reset_requests.sql` | `delete` 추가 | 4 |
| `app/core/cleanup.py` | 정리 단계 추가 | 4 |
| `tests/test_core_cleanup.py` | 정리 검증 | 4 |
| `README.md` | 운영자용 설명 | 5 |

---

## Task 1: 테이블 · 모델 · 마이그레이션

**Files:**
- Create: `app/models/password_reset_request.py`
- Modify: `app/models/__init__.py`
- Create: `alembic/versions/<autogenerate가 정하는 이름>.py`
- Modify: `docs/schema.sql` (`password_reset_codes` 블록 뒤, `CREATE TABLE faqs` 앞)
- Test: `tests/test_password_reset_request_model.py` (신규)

**Interfaces:**
- Consumes: `app.models.base`의 `BaseEntity`·`created_at_field()`·`created_by_field()`·`updated_at_field()`·`updated_by_field()`
- Produces:
  - `app.models.password_reset_request.PasswordResetRequest` — `__tablename__ = "password_reset_requests"`
  - 컬럼: `id`(BIGINT PK) · `email`(VARCHAR NOT NULL, index) · `client_ip`(VARCHAR NULL, index) · `created_at` · `created_by` · `updated_at` · `updated_by`
  - 인덱스명: `ix_password_reset_requests_email`, `ix_password_reset_requests_client_ip`

---

- [ ] **Step 1: 실패하는 테스트를 쓴다**

`tests/test_password_reset_request_model.py`를 새로 만든다:

```python
from app.models.password_reset_request import PasswordResetRequest


def test_column_order_is_id_business_audit():
    """테이블 생성 규칙: id → 업무 컬럼 → 생성/수정 감사 컬럼."""
    assert list(PasswordResetRequest.__table__.columns.keys()) == [
        "id",
        "email",
        "client_ip",
        "created_at",
        "created_by",
        "updated_at",
        "updated_by",
    ]


def test_client_ip_is_nullable():
    """IP를 알 수 없는 요청도 기록해야 한다 — 그래야 이메일 축이 계속 동작한다."""
    assert PasswordResetRequest.__table__.columns["client_ip"].nullable is True
    assert PasswordResetRequest.__table__.columns["email"].nullable is False


def test_email_and_ip_are_indexed():
    """판정 쿼리가 이 두 인덱스로 좁힌다. 없으면 공격 중에 seq scan이 된다."""
    indexed = {
        column.name
        for index in PasswordResetRequest.__table__.indexes
        for column in index.columns
    }
    assert indexed == {"email", "client_ip"}


async def test_audit_columns_are_filled_by_db_default(db_session):
    """created_at/updated_at은 DB server_default가 채운다(Asia/Seoul 벽시계 시각)."""
    row = PasswordResetRequest(email="a@example.com", client_ip="127.0.0.1")
    db_session.add(row)
    await db_session.commit()
    await db_session.refresh(row)

    assert row.id is not None
    assert row.created_at is not None
    assert row.updated_at is not None
```

- [ ] **Step 2: 테스트가 실패하는 것을 확인한다**

Run: `.venv/Scripts/python.exe -m pytest tests/test_password_reset_request_model.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.models.password_reset_request'`

- [ ] **Step 3: 모델을 만든다**

`app/models/password_reset_request.py`를 새로 만든다:

```python
from datetime import datetime
from typing import Optional

from sqlmodel import Field

from app.models.base import (
    BaseEntity,
    created_at_field,
    created_by_field,
    updated_at_field,
    updated_by_field,
)


class PasswordResetRequest(BaseEntity, table=True):
    __tablename__ = "password_reset_requests"
    __table_args__ = {"comment": "비밀번호 재설정 요청 이력 (rate limit 판정의 원장)"}

    email: str = Field(
        index=True,
        sa_column_kwargs={
            "comment": "정규화된(strip().lower()) 제출 이메일. 계정 존재와 무관하게 기록",
        },
    )
    client_ip: Optional[str] = Field(
        default=None,
        index=True,
        sa_column_kwargs={
            "comment": "요청자 IP (request.client.host). 알 수 없으면 NULL — 이때 IP 축은 꺼진다",
        },
    )

    created_at: Optional[datetime] = created_at_field()
    created_by: Optional[int] = created_by_field()
    updated_at: Optional[datetime] = updated_at_field()
    updated_by: Optional[int] = updated_by_field()
```

> 이 테이블에는 `requested_at`을 따로 두지 않는다. `created_at`이 곧 요청 시각이고, 하나 더 두면 같은 뜻의 컬럼이 둘이 되어 어느 쪽이 진짜인지 매번 확인해야 한다.

- [ ] **Step 4: 모델을 등록한다**

`app/models/__init__.py`에서 `PasswordResetCode` import 줄 **바로 아래**에 추가한다(알파벳 순):

```python
from app.models.password_reset_request import PasswordResetRequest
```

그리고 `__all__` 리스트의 `"PasswordResetCode",` **바로 아래**에 추가한다:

```python
    "PasswordResetRequest",
```

> 여기 등록해야 `tests/conftest.py`의 `SQLModel.metadata.create_all`이 테이블을 만들고, Alembic autogenerate도 이 테이블을 본다.

- [ ] **Step 5: 테스트가 통과하는 것을 확인한다**

Run: `.venv/Scripts/python.exe -m pytest tests/test_password_reset_request_model.py -v`
Expected: PASS (4개)

- [ ] **Step 6: Alembic 리비전을 만든다**

DB가 떠 있어야 한다:

Run: `docker compose up -d db`

그다음 자동 생성한다:

Run: `.venv/Scripts/python.exe -m alembic revision --autogenerate -m "add password reset requests"`

> 현재 head는 `ad49607788dd`(비밀번호 재설정 코드 테이블)다. 생성된 파일의 `down_revision`이 그 값인지 확인한다.

생성된 파일의 `upgrade()`가 아래와 **같은 내용인지 확인한다**(컬럼 순서·comment·인덱스 2개):

```python
def upgrade() -> None:
    op.create_table('password_reset_requests',
    sa.Column('id', sa.BigInteger(), autoincrement=True, nullable=False, comment='기본키, BIGINT 자동 증가'),
    sa.Column('email', sqlmodel.sql.sqltypes.AutoString(), nullable=False, comment='정규화된(strip().lower()) 제출 이메일. 계정 존재와 무관하게 기록'),
    sa.Column('client_ip', sqlmodel.sql.sqltypes.AutoString(), nullable=True, comment='요청자 IP (request.client.host). 알 수 없으면 NULL — 이때 IP 축은 꺼진다'),
    sa.Column('created_at', sa.DateTime(), server_default=sa.text("timezone('Asia/Seoul', now())"), nullable=False, comment='생성일시 (로컬 벽시계 시각, Asia/Seoul 기준, timezone 정보 없음)'),
    sa.Column('created_by', sa.BigInteger(), nullable=True, comment='생성자'),
    sa.Column('updated_at', sa.DateTime(), server_default=sa.text("timezone('Asia/Seoul', now())"), nullable=False, comment='수정일시 (로컬 벽시계 시각, 수정 시 갱신)'),
    sa.Column('updated_by', sa.BigInteger(), nullable=True, comment='수정자'),
    sa.PrimaryKeyConstraint('id'),
    comment='비밀번호 재설정 요청 이력 (rate limit 판정의 원장)'
    )
    op.create_index(op.f('ix_password_reset_requests_client_ip'), 'password_reset_requests', ['client_ip'], unique=False)
    op.create_index(op.f('ix_password_reset_requests_email'), 'password_reset_requests', ['email'], unique=False)
```

다른 테이블에 대한 변경(`op.drop_*`·`op.alter_*`)이 섞여 나왔다면 **지운다** — 이 리비전은 새 테이블 하나만 다룬다.

- [ ] **Step 7: 마이그레이션을 적용해 본다**

Run: `.venv/Scripts/python.exe -m alembic upgrade head`
Expected: 오류 없이 끝난다.

되돌리기도 동작하는지 확인한다:

Run: `.venv/Scripts/python.exe -m alembic downgrade -1`
Expected: 오류 없이 끝난다.

Run: `.venv/Scripts/python.exe -m alembic upgrade head`
Expected: 다시 적용된다.

- [ ] **Step 8: `docs/schema.sql`을 갱신한다**

`COMMENT ON COLUMN password_reset_codes.updated_by IS '수정자';` 줄 **다음**, `CREATE TABLE faqs (` **앞**에 넣는다:

```sql
CREATE TABLE password_reset_requests (
    id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    email VARCHAR NOT NULL,
    client_ip VARCHAR,
    created_at TIMESTAMP NOT NULL DEFAULT (timezone('Asia/Seoul', now())),
    created_by BIGINT,
    updated_at TIMESTAMP NOT NULL DEFAULT (timezone('Asia/Seoul', now())),
    updated_by BIGINT
);

CREATE INDEX ix_password_reset_requests_email ON password_reset_requests (email);
CREATE INDEX ix_password_reset_requests_client_ip ON password_reset_requests (client_ip);

COMMENT ON TABLE password_reset_requests IS '비밀번호 재설정 요청 이력 (rate limit 판정의 원장)';
COMMENT ON COLUMN password_reset_requests.id IS '기본키, BIGINT 자동 증가';
COMMENT ON COLUMN password_reset_requests.email IS '정규화된(strip().lower()) 제출 이메일. 계정 존재와 무관하게 기록';
COMMENT ON COLUMN password_reset_requests.client_ip IS '요청자 IP (request.client.host). 알 수 없으면 NULL — 이때 IP 축은 꺼진다';
COMMENT ON COLUMN password_reset_requests.created_at IS '생성일시 (로컬 벽시계 시각, Asia/Seoul 기준, timezone 정보 없음)';
COMMENT ON COLUMN password_reset_requests.created_by IS '생성자';
COMMENT ON COLUMN password_reset_requests.updated_at IS '수정일시 (로컬 벽시계 시각, 수정 시 갱신)';
COMMENT ON COLUMN password_reset_requests.updated_by IS '수정자';
```

- [ ] **Step 9: 커밋**

```bash
git add app/models/password_reset_request.py app/models/__init__.py alembic/versions docs/schema.sql tests/test_password_reset_request_model.py
git commit -m "feat: 재설정 요청 이력 테이블 추가"
```

---

## Task 2: 한도 설정 · 판정 모듈

**Files:**
- Modify: `app/config.py` (`Settings`에 필드 3개)
- Modify: `.env.example` (파일 끝에 추가)
- Create: `app/queries/password_reset_requests.sql`
- Create: `app/auth/reset_rate_limit.py`
- Test: `tests/test_reset_rate_limit.py` (신규)

**Interfaces:**
- Consumes: Task 1의 `password_reset_requests` 테이블, `app.config.get_settings()`, `app.queries.queries`, `app.utils.errors.AppError`
- Produces:
  - `Settings.reset_request_cooldown_sec`(int) · `reset_request_email_hourly`(int) · `reset_request_ip_hourly`(int)
  - `app.auth.reset_rate_limit.RESET_REQUEST_WINDOW_MINUTES = 60` (Task 4가 정리 cutoff로 쓴다)
  - `app.auth.reset_rate_limit.check_and_record(conn, email: str, client_ip: str | None, now: datetime) -> None` — 한도 초과면 `AppError(429, "TOO_MANY_RESET_REQUESTS", ...)`를 던지고, 아니면 행 1건을 INSERT한다. 커밋은 **하지 않는다**(호출자 책임).
  - 쿼리 `insert_reset_request` · `count_recent_reset_requests`

---

- [ ] **Step 1: `Settings`에 한도 3개를 추가한다**

`app/config.py` 맨 위 import를 바꾼다:

```python
from pydantic import Field, field_validator
```

`smtp_timeout_sec: int = 15` 줄 **바로 아래**에 넣는다:

```python
    # --- 비밀번호 재설정 요청 제한 ---
    # 창은 1시간 고정이다(키 이름에 들어 있다). 세 값 모두 "1시간에 허용하는 최대
    # 통과 횟수"이고, 판정은 >= 다 — EMAIL_HOURLY=5면 6번째 요청이 거부된다.
    # 0을 허용하는 것은 쿨다운뿐이다(0 = 쿨다운 끔). 나머지를 0으로 두면 아무도
    # 재설정할 수 없게 되므로 하한이 1이다.
    reset_request_cooldown_sec: int = Field(default=60, ge=0, le=3600)
    reset_request_email_hourly: int = Field(default=5, ge=1, le=100)
    reset_request_ip_hourly: int = Field(default=20, ge=1, le=1000)
```

- [ ] **Step 2: 쿼리 파일을 만든다**

`app/queries/password_reset_requests.sql`을 새로 만든다:

```sql
-- name: insert_reset_request<!
-- created_at을 명시해서 넣는다. 판정에 쓴 시각과 기록되는 시각이 같아야 하고,
-- 테스트가 과거 요청을 만들 때 같은 쿼리를 쓸 수 있어야 한다.
INSERT INTO password_reset_requests (email, client_ip, created_at, updated_at)
VALUES (:email, :client_ip, :created_at, :updated_at)
RETURNING id;

-- name: count_recent_reset_requests^
-- rate limit 세 축을 한 번의 스캔으로 센다.
--
-- 바깥 WHERE가 email/client_ip 인덱스를 타도록 좁혀 두었으므로, email_window와
-- ip_window의 FILTER에서는 created_at 조건을 반복하지 않는다 — 바깥에서 이미
-- 걸러졌다. 쿨다운만 더 좁은 창이라 한 번 더 건다(cooldown_since >= window_since가
-- 항상 성립하므로 집합이 어긋나지 않는다).
--
-- client_ip가 NULL이면 SQL에서 client_ip = NULL이 어떤 행과도 매치되지 않아
-- IP 축이 저절로 꺼진다 — 식별할 수 없는 것을 제한하지 않는다는 뜻이고,
-- 이를 위한 분기를 파이썬에 두지 않는다.
SELECT
    COUNT(*) FILTER (WHERE email = :email AND created_at > :cooldown_since) AS email_cooldown,
    COUNT(*) FILTER (WHERE email = :email)                                  AS email_window,
    COUNT(*) FILTER (WHERE client_ip = :client_ip)                          AS ip_window
FROM password_reset_requests
WHERE (email = :email OR client_ip = :client_ip)
  AND created_at > :window_since;
```

> `:email`이 세 번, `:client_ip`가 두 번 나오지만 문제없다. aiosql의 asyncpg 어댑터는 이미 본 이름을 같은 `$n`으로 재사용한다.

- [ ] **Step 3: 실패하는 테스트를 쓴다**

`tests/test_reset_rate_limit.py`를 새로 만든다:

```python
from datetime import timedelta

import pytest

from app.auth.reset_rate_limit import RESET_REQUEST_WINDOW_MINUTES, check_and_record
from app.config import get_settings
from app.db import raw_connection
from app.queries import queries
from app.utils.errors import AppError
from app.utils.time import now_local


@pytest.fixture
def limits(monkeypatch):
    """한도를 테스트가 다루기 쉬운 작은 값으로 못박는다(로컬 .env에 흔들리지 않게)."""
    monkeypatch.setenv("RESET_REQUEST_COOLDOWN_SEC", "60")
    monkeypatch.setenv("RESET_REQUEST_EMAIL_HOURLY", "5")
    monkeypatch.setenv("RESET_REQUEST_IP_HOURLY", "20")
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


async def _record_at(conn, email, client_ip, when):
    """과거 요청을 직접 심는다. sleep으로 기다리지 않는다."""
    await queries.insert_reset_request(
        conn, email=email, client_ip=client_ip, created_at=when, updated_at=when
    )


async def test_first_request_passes_and_is_recorded(db_session, limits):
    conn = await raw_connection(db_session)
    now = now_local()

    await check_and_record(conn, "a@example.com", "1.1.1.1", now)

    row = await queries.count_recent_reset_requests(
        conn,
        email="a@example.com",
        client_ip="1.1.1.1",
        cooldown_since=now - timedelta(seconds=60),
        window_since=now - timedelta(minutes=RESET_REQUEST_WINDOW_MINUTES),
    )
    assert row["email_window"] == 1


async def test_second_request_within_cooldown_is_rejected(db_session, limits):
    conn = await raw_connection(db_session)
    now = now_local()
    await check_and_record(conn, "a@example.com", "1.1.1.1", now)

    with pytest.raises(AppError) as exc:
        await check_and_record(conn, "a@example.com", "1.1.1.1", now + timedelta(seconds=30))

    assert exc.value.status_code == 429
    assert exc.value.code == "TOO_MANY_RESET_REQUESTS"


async def test_request_after_cooldown_passes(db_session, limits):
    conn = await raw_connection(db_session)
    now = now_local()
    await check_and_record(conn, "a@example.com", "1.1.1.1", now)

    await check_and_record(conn, "a@example.com", "1.1.1.1", now + timedelta(seconds=61))


async def test_email_hourly_limit(db_session, limits):
    conn = await raw_connection(db_session)
    now = now_local()
    # 쿨다운에 걸리지 않도록 5분 간격으로 5건을 심는다.
    for i in range(5):
        await _record_at(conn, "a@example.com", "1.1.1.1", now - timedelta(minutes=5 * (i + 1)))

    with pytest.raises(AppError) as exc:
        await check_and_record(conn, "a@example.com", "1.1.1.1", now)

    assert exc.value.status_code == 429


async def test_email_limit_ignores_requests_outside_the_window(db_session, limits):
    conn = await raw_connection(db_session)
    now = now_local()
    # 창(1시간) 밖의 5건은 세지 않는다.
    for i in range(5):
        await _record_at(conn, "a@example.com", "1.1.1.1", now - timedelta(minutes=61 + i))

    await check_and_record(conn, "a@example.com", "1.1.1.1", now)


async def test_ip_hourly_limit_across_different_emails(db_session, limits):
    """이메일을 바꿔가며 때려도 IP 축에 걸린다 — 발신 계정 하루 한도를 지킨다."""
    conn = await raw_connection(db_session)
    now = now_local()
    for i in range(20):
        await _record_at(conn, f"user{i}@example.com", "9.9.9.9", now - timedelta(minutes=i + 1))

    with pytest.raises(AppError) as exc:
        await check_and_record(conn, "fresh@example.com", "9.9.9.9", now)

    assert exc.value.status_code == 429


async def test_unknown_ip_disables_the_ip_axis(db_session, limits):
    """IP를 알 수 없어도 이메일 축은 계속 동작해야 한다."""
    conn = await raw_connection(db_session)
    now = now_local()
    for i in range(20):
        await _record_at(conn, f"user{i}@example.com", None, now - timedelta(minutes=i + 1))

    # IP 축은 꺼지므로 새 이메일은 통과한다.
    await check_and_record(conn, "fresh@example.com", None, now)


async def test_rejected_request_is_not_recorded(db_session, limits):
    """거부까지 기록하면 공격이 이어지는 동안 창이 밀려 피해자가 영영 못 푼다."""
    conn = await raw_connection(db_session)
    now = now_local()
    await check_and_record(conn, "a@example.com", "1.1.1.1", now)

    # 쿨다운 안에서 10번 두들긴다 — 전부 거부되고 아무것도 기록되지 않아야 한다.
    for i in range(10):
        with pytest.raises(AppError):
            await check_and_record(conn, "a@example.com", "1.1.1.1", now + timedelta(seconds=i + 1))

    # 쿨다운만 지나면 곧바로 통과한다(창이 밀리지 않았다).
    await check_and_record(conn, "a@example.com", "1.1.1.1", now + timedelta(seconds=61))


async def test_same_email_string_shares_one_bucket(db_session, limits):
    """같은 문자열은 같은 버킷이다.

    이 함수는 정규화하지 않는다 — 정규화는 호출자(라우터)의 책임이고, 대소문자가
    실제로 합쳐지는지는 tests/test_password_reset_request.py가 엔드포인트에서 본다.
    """
    conn = await raw_connection(db_session)
    now = now_local()
    await check_and_record(conn, "a@example.com", "1.1.1.1", now)

    with pytest.raises(AppError):
        await check_and_record(conn, "a@example.com", "1.1.1.1", now + timedelta(seconds=10))


async def test_cooldown_zero_disables_cooldown(db_session, monkeypatch):
    monkeypatch.setenv("RESET_REQUEST_COOLDOWN_SEC", "0")
    monkeypatch.setenv("RESET_REQUEST_EMAIL_HOURLY", "5")
    monkeypatch.setenv("RESET_REQUEST_IP_HOURLY", "20")
    get_settings.cache_clear()
    try:
        conn = await raw_connection(db_session)
        now = now_local()
        await check_and_record(conn, "a@example.com", "1.1.1.1", now)
        # 쿨다운이 꺼졌으므로 같은 시각에 한 번 더 해도 통과한다(시간당 한도까지).
        await check_and_record(conn, "a@example.com", "1.1.1.1", now)
    finally:
        get_settings.cache_clear()


async def test_failure_log_names_the_axis_but_response_does_not(db_session, limits, caplog):
    """어느 축에 걸렸는지는 서버 로그에만 남긴다. 응답으로 구분해 주면 우회 경로를 알려주는 셈이다."""
    conn = await raw_connection(db_session)
    now = now_local()
    await check_and_record(conn, "a@example.com", "1.1.1.1", now)

    with caplog.at_level("WARNING"):
        with pytest.raises(AppError) as exc:
            await check_and_record(conn, "a@example.com", "1.1.1.1", now + timedelta(seconds=1))

    assert "cooldown" in caplog.text
    assert "cooldown" not in exc.value.message
```

- [ ] **Step 4: 테스트가 실패하는 것을 확인한다**

Run: `.venv/Scripts/python.exe -m pytest tests/test_reset_rate_limit.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.auth.reset_rate_limit'` (수집 단계에서 전부 에러)

- [ ] **Step 5: 판정 모듈을 만든다**

`app/auth/reset_rate_limit.py`를 새로 만든다:

```python
import logging
from datetime import datetime, timedelta

from app.config import get_settings
from app.queries import queries
from app.utils.errors import AppError

logger = logging.getLogger(__name__)

# 이메일·IP 시간당 한도의 창. 설정 키 이름(`..._HOURLY`)에 이미 들어 있어 .env로 빼지 않는다.
RESET_REQUEST_WINDOW_MINUTES = 60

# 어느 축에 걸렸는지 응답으로 구분하지 않는다 — 구분해 주면 공격자가 어느 축을
# 우회해야 하는지 알게 된다.
_TOO_MANY = AppError(
    429, "TOO_MANY_RESET_REQUESTS", "요청이 너무 잦습니다. 잠시 후 다시 시도해 주세요."
)


async def check_and_record(conn, email: str, client_ip: str | None, now: datetime) -> None:
    """재설정 요청 한도를 보고, 통과하면 이번 요청을 기록한다.

    호출자는 **계정을 조회하기 전에** 이 함수를 불러야 한다. 발송이 일어날 때만
    제한하면 429를 받았다는 사실이 곧 "그 계정은 존재한다"가 되어, 응답 본문을
    통일해 지켜 온 계정 열거 방지가 깨진다.

    email은 **정규화된**(strip().lower()) 값이어야 한다. 아니면 대소문자만 바꿔
    제한을 무한히 우회할 수 있다.

    거부된 요청은 기록하지 않는다. 기록하면 공격자가 때리는 동안 창이 끝없이 밀려
    피해자가 영원히 재설정하지 못한다 — 보호 장치가 그대로 공격 도구가 된다.

    커밋하지 않는다. 호출자가 커밋 시점을 정한다.
    """
    settings = get_settings()
    row = await queries.count_recent_reset_requests(
        conn,
        email=email,
        client_ip=client_ip,
        cooldown_since=now - timedelta(seconds=settings.reset_request_cooldown_sec),
        window_since=now - timedelta(minutes=RESET_REQUEST_WINDOW_MINUTES),
    )

    # 판정은 셋 다 >= 다. 설정값은 "1시간에 허용하는 최대 통과 횟수"라,
    # EMAIL_HOURLY=5면 5건이 쌓인 시점의 6번째가 거부된다.
    if row["email_cooldown"] >= 1:
        axis = "cooldown"
    elif row["email_window"] >= settings.reset_request_email_hourly:
        axis = "email"
    elif row["ip_window"] >= settings.reset_request_ip_hourly:
        axis = "ip"
    else:
        axis = None

    if axis is not None:
        # 감사 로그에는 남기지 않는다 — 무차별 공격 시 로그가 넘치고, 그건 재설정
        # 설계 §2.4가 요청·실패를 기록하지 않기로 한 이유와 같다. 어느 축인지는
        # 운영자가 대응하려면 필요하므로 서버 로그에만 남긴다.
        logger.warning(
            "재설정 요청 한도 초과: axis=%s email=%s ip=%s", axis, email, client_ip
        )
        raise _TOO_MANY

    await queries.insert_reset_request(
        conn, email=email, client_ip=client_ip, created_at=now, updated_at=now
    )
```

- [ ] **Step 6: 테스트가 통과하는 것을 확인한다**

Run: `.venv/Scripts/python.exe -m pytest tests/test_reset_rate_limit.py -v`
Expected: PASS (11개)

- [ ] **Step 7: `.env.example`에 3개를 추가한다**

파일 맨 아래(`SMTP_TIMEOUT_SEC=15` 다음)에 붙인다:

```
# 비밀번호 재설정 요청 제한 — 실제 메일이 나가므로 요청 빈도에 상한이 필요하다.
# 세 값 모두 "1시간에 허용하는 최대 통과 횟수"다. 창은 1시간 고정.
# 같은 이메일로 재요청할 수 있는 최소 간격(초). 허용: 0~3600 (0이면 간격 제한 끔)
RESET_REQUEST_COOLDOWN_SEC=60
# 같은 이메일로 1시간에 허용할 요청 수. 허용: 1~100
RESET_REQUEST_EMAIL_HOURLY=5
# 같은 IP로 1시간에 허용할 요청 수. 허용: 1~1000
RESET_REQUEST_IP_HOURLY=20
```

- [ ] **Step 8: 커밋**

```bash
git add app/config.py .env.example app/queries/password_reset_requests.sql app/auth/reset_rate_limit.py tests/test_reset_rate_limit.py
git commit -m "feat: 재설정 요청 rate limit 판정 모듈 추가"
```

---

## Task 3: 라우터 통합

**Files:**
- Modify: `app/auth/router.py` (import 1줄, 엔드포인트 시그니처와 본문 앞부분)
- Test: `tests/test_password_reset_request.py` (테스트 5개 추가)

**Interfaces:**
- Consumes: Task 2의 `check_and_record(conn, email, client_ip, now)`
- Produces: `POST /api/auth/password-reset/request`가 한도 초과 시 `429 {"code": "TOO_MANY_RESET_REQUESTS", "message": "요청이 너무 잦습니다. 잠시 후 다시 시도해 주세요."}`를 반환한다. 한도 안에서는 기존 동작(항상 200 + 통일 메시지, 발송은 백그라운드)이 그대로다.
- `Request`는 `app/auth/router.py`에 **이미 import되어 있다**(4행). 새로 추가하지 않는다.

---

- [ ] **Step 1: 실패하는 테스트를 쓴다**

`tests/test_password_reset_request.py` 맨 아래에 추가한다:

```python
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
```

- [ ] **Step 2: 테스트가 실패하는 것을 확인한다**

Run: `.venv/Scripts/python.exe -m pytest tests/test_password_reset_request.py -v -k "429 or rate or forwarded or bucket or unknown_email_is"`
Expected: FAIL — 아직 제한이 없어 두 번째 요청도 200이다.

- [ ] **Step 3: 라우터를 고친다**

`app/auth/router.py`의 `from app.auth.password_reset import (...)` 블록 **바로 아래**에 import를 추가한다:

```python
from app.auth.reset_rate_limit import check_and_record
```

`password_reset_request` 함수 시그니처에 `request: Request`를 더한다:

```python
@router.post("/password-reset/request")
async def password_reset_request(
    body: PasswordResetRequest,
    background: BackgroundTasks,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
```

> `Request`는 기본값이 없으므로 `db=Depends(...)` **앞**에 와야 한다.

본문 앞부분(`email = ...`부터 `row = ...`까지)을 다음으로 바꾼다:

```python
    email = body.email.strip().lower()
    conn = await raw_connection(db)

    # 계정을 조회하기 **전에** 판정한다. 발송이 일어날 때만 제한하면 429가 곧
    # "그 계정은 존재한다"가 되어, 응답 본문을 통일해 막아 둔 계정 열거가 깨진다.
    #
    # IP는 request.client.host만 쓴다 — X-Forwarded-For를 읽지 않는 이유는 감사
    # 로그(app/core/audit.py)와 같고, 여기서는 더 치명적이다. 프록시가 없는 배포에서
    # 그 헤더를 믿으면 값만 바꿔가며 IP 축을 통째로 우회할 수 있다.
    await check_and_record(
        conn, email, request.client.host if request.client else None, now_local()
    )
    # 기록을 즉시 커밋한다. 아래 발송 경로의 커밋은 계정이 있을 때만 일어나므로,
    # 여기서 커밋하지 않으면 미존재 이메일에 대한 기록이 롤백되어 제한이 무력해진다.
    await db.commit()

    row = await queries.find_by_email(conn, email=email)
```

- [ ] **Step 4: 테스트가 통과하는 것을 확인한다**

Run: `.venv/Scripts/python.exe -m pytest tests/test_password_reset_request.py -v`
Expected: PASS (14개 — 기존 8개 + 새 6개)

> 기존 테스트 중 같은 이메일로 두 번 요청하는 `test_request_invalidates_previous_code`가 쿨다운에 걸려 깨질 수 있다. 깨지면 두 요청 사이에 `RESET_REQUEST_COOLDOWN_SEC=0`을 적용하는 것이 아니라, **그 테스트에만** `monkeypatch.setenv("RESET_REQUEST_COOLDOWN_SEC", "0")` + `get_settings.cache_clear()`를 넣어 쿨다운을 끈다. 그 테스트가 검증하려는 것은 코드 무효화이지 쿨다운이 아니다.

- [ ] **Step 5: 재설정 관련 테스트 전체를 돌린다**

Run: `.venv/Scripts/python.exe -m pytest tests/test_password_reset_request.py tests/test_password_reset_verify.py tests/test_password_reset_confirm.py tests/test_password_reset_deliver.py tests/test_reset_rate_limit.py tests/test_email.py -v`
Expected: 전부 PASS

- [ ] **Step 6: 커밋**

```bash
git add app/auth/router.py tests/test_password_reset_request.py
git commit -m "feat: 재설정 요청에 rate limit 적용"
```

---

## Task 4: 정리 잡

**Files:**
- Modify: `app/queries/password_reset_requests.sql` (쿼리 1개 추가)
- Modify: `app/core/cleanup.py` (함수 1개 + `run_once`에 호출 1줄)
- Test: `tests/test_core_cleanup.py` (테스트 2개 추가)

**Interfaces:**
- Consumes: Task 2의 `RESET_REQUEST_WINDOW_MINUTES`
- Produces: `app.core.cleanup._purge_old_reset_requests(session)`, 쿼리 `delete_old_reset_requests`
- `cleanup.py`는 `timedelta`(3행)와 `now_local`(10행)을 **이미 import하고 있다.**

---

- [ ] **Step 1: 삭제 쿼리를 추가한다**

`app/queries/password_reset_requests.sql` 맨 아래에 붙인다:

```sql
-- name: delete_old_reset_requests!
-- 정리 잡이 쓴다. cutoff는 가장 긴 rate limit 창(1시간) 이전 — 그보다 오래된 행은
-- 어떤 판정에도 쓰이지 않는다. 별도 보관 기간 상수를 두지 않는 이유가 이것이다
-- (기준이 창 자체라 정책 판단이 없다 — 재설정 코드 정리와 같은 방침).
DELETE FROM password_reset_requests WHERE created_at < :cutoff;
```

- [ ] **Step 2: 실패하는 테스트를 쓴다**

`tests/test_core_cleanup.py` 맨 아래에 추가한다:

```python
# ─── 재설정 요청 이력 정리 ───


async def test_reset_requests_older_than_the_window_are_purged(db_session):
    conn = await raw_connection(db_session)
    old = now_local() - timedelta(minutes=61)
    await queries.insert_reset_request(
        conn, email="old@example.com", client_ip="1.1.1.1", created_at=old, updated_at=old
    )
    await db_session.commit()

    await run_once(_factory(db_session))

    row = await queries.count_recent_reset_requests(
        conn,
        email="old@example.com",
        client_ip="1.1.1.1",
        cooldown_since=now_local() - timedelta(days=1),
        window_since=now_local() - timedelta(days=1),
    )
    assert row["email_window"] == 0


async def test_reset_requests_inside_the_window_are_kept(db_session):
    """진행 중인 제한을 정리 잡이 풀어주면 안 된다 — 그 순간 폭탄이 다시 열린다."""
    conn = await raw_connection(db_session)
    recent = now_local() - timedelta(minutes=5)
    await queries.insert_reset_request(
        conn, email="recent@example.com", client_ip="2.2.2.2", created_at=recent, updated_at=recent
    )
    await db_session.commit()

    await run_once(_factory(db_session))

    row = await queries.count_recent_reset_requests(
        conn,
        email="recent@example.com",
        client_ip="2.2.2.2",
        cooldown_since=now_local() - timedelta(seconds=60),
        window_since=now_local() - timedelta(minutes=60),
    )
    assert row["email_window"] == 1
```

> `timedelta`·`now_local`·`raw_connection`·`queries`·`run_once`·`_factory`는 이 파일이 기존 테스트에서 이미 쓰고 있다. 없다면 파일 상단 import를 확인한다.

- [ ] **Step 3: 테스트가 실패하는 것을 확인한다**

Run: `.venv/Scripts/python.exe -m pytest tests/test_core_cleanup.py -v -k reset_requests`
Expected: FAIL — `test_reset_requests_older_than_the_window_are_purged`가 `1 == 0`으로 깨진다(정리 단계가 아직 없어 오래된 행이 남는다).

- [ ] **Step 4: 정리 단계를 구현한다**

`app/core/cleanup.py`의 `_purge_expired_reset_codes` 함수 **바로 아래**에 추가한다:

```python
async def _purge_old_reset_requests(session) -> None:
    """rate limit 창을 벗어난 재설정 요청 기록을 지운다.

    창(1시간)보다 오래된 행은 어떤 판정에도 쓰이지 않으므로, 지워도 제한이 느슨해지지
    않는다. 판정 쿼리가 created_at > window_since로 이미 거르기 때문에 남아 있어도
    결과는 같다 — 이 정리는 테이블 크기에 상한을 씌우는 것이 전부다.

    잡이 24시간 주기라 그 사이에는 최대 24시간치가 쌓인다. 그래도 판정이 느려지지
    않는 것은 email·client_ip 인덱스로 좁힌 뒤 세기 때문이다.

    건수를 로그로 남기지 않는 것은 _purge_expired_reset_codes와 같은 이유다 —
    한 시간마다 갈리는 부산물이라 건수에 운영 신호가 없다.
    """
    conn = await raw_connection(session)
    cutoff = now_local() - timedelta(minutes=RESET_REQUEST_WINDOW_MINUTES)
    await queries.delete_old_reset_requests(conn, cutoff=cutoff)
    await session.commit()
```

파일 상단 import에 한 줄 추가한다(`from app.core import audit` 아래):

```python
from app.auth.reset_rate_limit import RESET_REQUEST_WINDOW_MINUTES
```

> 순환 import는 없다. `app.auth.reset_rate_limit`은 `app.config`·`app.queries`·`app.utils.errors`만 가져온다.

`run_once`에서 `_purge_expired_reset_codes` 호출 **바로 뒤**에 자기 세션으로 넣는다:

```python
    async with factory() as session:
        await _purge_expired_reset_codes(session)

    async with factory() as session:
        await _purge_old_reset_requests(session)        # 신규

    async with factory() as session:
        await _purge_old_audit_logs(session)
```

- [ ] **Step 5: 테스트가 통과하는 것을 확인한다**

Run: `.venv/Scripts/python.exe -m pytest tests/test_core_cleanup.py -v`
Expected: 전부 PASS (기존 + 새 2개)

- [ ] **Step 6: 커밋**

```bash
git add app/queries/password_reset_requests.sql app/core/cleanup.py tests/test_core_cleanup.py
git commit -m "feat: 창을 벗어난 재설정 요청 기록 정리"
```

---

## Task 5: 문서

**Files:**
- Modify: `README.md` (`### 비밀번호 재설정` 절 끝)

**Interfaces:**
- Consumes: 없음
- Produces: 없음 (동작 변화 없는 마무리 작업)

---

- [ ] **Step 1: README에 rate limit 설명을 더한다**

`README.md`의 `### 비밀번호 재설정` 절에서, 만료 코드 정리를 설명하는 마지막 문장(`만료된 코드는 정리 잡이 하루 한 번 지운다...`) **다음**에 붙인다:

```markdown
요청 빈도에는 상한이 있다(`app/auth/reset_rate_limit.py`). 실제 메일이 나가므로, 제한이 없으면 남의 주소로 요청을 반복해 그 사람 메일함을 채우거나 발신 계정의 하루 한도를 태워 정상 사용자까지 코드를 못 받게 만들 수 있다.

| `.env` 키 | 기본값 | 뜻 |
|---|---|---|
| `RESET_REQUEST_COOLDOWN_SEC` | 60 | 같은 이메일로 재요청할 수 있는 최소 간격(초). 0이면 끔 |
| `RESET_REQUEST_EMAIL_HOURLY` | 5 | 같은 이메일로 1시간에 허용할 요청 수 |
| `RESET_REQUEST_IP_HOURLY` | 20 | 같은 IP로 1시간에 허용할 요청 수 |

초과하면 `429 TOO_MANY_RESET_REQUESTS`를 통일된 문구로 돌려준다. **판정은 계정을 조회하기 전에** 하므로 429가 계정 존재를 알려주지 않고, **거부된 요청은 기록하지 않으므로** 공격이 이어져도 창이 밀리지 않는다(밀린다면 피해자가 영영 재설정하지 못한다). 어느 축에 걸렸는지는 서버 로그에만 남는다.

IP는 감사 로그와 같이 `request.client.host`만 본다 — 프록시 없는 단독 배포라 `X-Forwarded-For`를 신뢰하면 헤더 한 줄로 IP 축이 무력해진다. 프록시 뒤에 두는 배포로 바뀌면 이 결정을 다시 봐야 한다.

이 이력은 `password_reset_requests` 테이블에 쌓이고, 창(1시간)을 벗어난 행은 정리 잡이 지운다.
```

- [ ] **Step 2: 프론트 빌드를 확인한다**

프론트 코드는 바꾸지 않았지만(429 메시지는 기존 `ApiError` 경로로 그대로 표시된다) 빌드가 깨지지 않았는지 본다.

Run: `cd web && npm run build`
Expected: `✓ built` 로 끝난다.

- [ ] **Step 3: 전체 테스트를 돌린다**

Run: `.venv/Scripts/python.exe -m pytest`
Expected: 전부 PASS

> 전체 실행에는 Docker가 필요하다(testcontainers Postgres 16). `PIXABAY_API_KEY`가 없으면 `tests/test_stock_smoke.py`의 2개는 기존과 같이 SKIP된다.

- [ ] **Step 4: 커밋**

```bash
git add README.md
git commit -m "docs: 재설정 요청 rate limit 설명 추가"
```

---

## 수동 검증 (전체 완료 후)

- [ ] 앱을 띄우고 로그인 화면 → "비밀번호를 잊으셨나요?" → 실재 이메일로 **연속 두 번** 요청한다.
- [ ] 두 번째에 팝업 안에 "요청이 너무 잦습니다. 잠시 후 다시 시도해 주세요."가 뜨는지 본다(프론트 수정 없이 표시돼야 한다).
- [ ] `log/studio/mail/`에 `.eml`이 **1개만** 생겼는지 확인한다.
- [ ] 60초 뒤 다시 요청해 통과하고 `.eml`이 하나 더 생기는지 확인한다.
- [ ] 서버 로그에 `재설정 요청 한도 초과: axis=cooldown ...`이 찍혔는지 확인한다.
- [ ] 가입하지 않은 주소로도 연속 두 번 요청해 똑같이 429가 나는지 확인한다(계정 존재가 새지 않는다).
