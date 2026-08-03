# 비밀번호 재설정(찾기) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 로그인 못 하는 사용자가 6자리 인증코드로 비밀번호를 새로 설정하는 플로우를 만든다. 코드 전달은 지금은 비워 두고(나중에 이메일 발송으로 채움), 생성·저장·검증·변경 뼈대를 완성한다.

**Architecture:** `refresh_tokens`와 같은 패턴의 새 테이블 `password_reset_codes`(만료·소비·시도 컬럼)에 6자리 코드를 문자열로 저장한다. 비로그인 엔드포인트 3개(`request`/`verify`/`confirm`)를 `app/auth/router.py`에 추가하고, 코드 생성·전달 로직은 `app/auth/password_reset.py`로 분리한다. 코드 전달은 `deliver_reset_code()` 함수 하나가 담당하며 — 이 함수가 이 기능의 **유일한 보안 경계**다. 프론트는 로그인 화면의 팝업(기존 `Modal`) 3단계.

**Tech Stack:** 기존 그대로 — Python 3.12, FastAPI, SQLModel(스키마), aiosql(`app/queries/*.sql`), Alembic, argon2/SHA-256(security.py), pytest+testcontainers / React + TypeScript + Tailwind, 기존 `Modal`·`api`·`usePasswordMinLen`.

**설계 문서:** `docs/superpowers/specs/2026-07-31-password-reset-design.md`

> **실행 중 변경(2026-07-31):** 아래 세 가지가 계획과 다르게 구현됐다. 스니펫보다 이 문단과 설계 문서가 우선이다.
>
> 1. **코드 저장:** SHA-256 해시 → **평문 문자열**(`code` VARCHAR, 000000~999999 6자리). 6자리는 해시해도 즉시 역산되어 실질 보호가 없고, 코드는 수량이 아니라 문자열(PIN)이라 VARCHAR가 자연스럽다(앞자리 0 보존). 따라서 아래 스니펫의 `code_hash`/`hash_reset_code`/`hmac.compare_digest`는 모두 무효다 — 실제 구현은 `code` 문자열을 직접 비교한다. 근거는 설계 문서 §2.1 "코드 저장 방식".
> 2. **코드 전달:** 콘솔 로그를 없애고 `deliver_reset_code()`를 no-op(이메일용 빈 자리)으로 두었다 — 아래 스니펫의 `logger.info`도 무효다. 개발 중엔 `password_reset_codes` 테이블에서 code를 직접 확인한다. 근거는 설계 문서 §0.
> 3. **엔드포인트·프론트 단계 추가:** 계획에 없던 **`POST /auth/password-reset/verify`**(코드 확인만, 소비·변경 없음)를 넣고 팝업을 **3단계**(email → code → password)로 만들었다. confirm이 같은 코드를 다시 검증하므로 verify는 UX 게이트일 뿐 보안 경계가 아니다. 검증 로직은 confirm과 공통 헬퍼 `_resolve_reset_code`로 묶었다. 테스트는 `tests/test_password_reset_verify.py`. 근거는 설계 문서 §2.2·§3.

## Global Constraints

- **보안 경고(설계 0장):** 이 기능은 이메일 발송이 붙기 전까지 실질 보안이 없다. 코드가 사용자에게 전달되는 경로가 없어 `password_reset_codes` 테이블을 볼 수 있는 사람만 재설정할 수 있으므로, 운영 배포 전 반드시 `deliver_reset_code()`를 이메일 발송으로 교체해야 한다. **API 응답에는 코드를 절대 싣지 않는다.**
- 코드: **6자리 숫자**, `secrets`로 생성(`f"{secrets.randbelow(1_000_000):06d}"`). 저장은 **평문 문자열**(`code` VARCHAR — 위 "실행 중 변경" 1번).
- 만료 **10분**. **1회용**(`consumed_at`). 검증 시도 **5회** 한도(초과 시 코드 무효화). **사용자당 활성 코드 1개**(새 요청이 이전 미소비 코드를 무효화).
- **계정 열거 방지:** `request`는 이메일 존재/상태와 무관하게 항상 동일한 200 응답. `confirm` 실패는 원인 불문 동일한 400(`INVALID_RESET_CODE`, "코드가 올바르지 않거나 만료되었습니다.").
- **상태 조건:** `DISABLED`/`REJECTED`는 코드를 발급하지 않되 응답은 동일. `PENDING`·`ACTIVE`는 발급.
- **성공 시:** 비밀번호 정책 검증(`get_runtime_settings(conn).password_min_len`, 미달 시 `WEAK_PASSWORD`) → argon2 해시로 갱신 → 코드 소비 → 그 사용자의 refresh 토큰 전부 폐기 → 로그인 잠금(`failed_login_count`, `locked_at`) 해제. `SAME_PASSWORD` 검사는 하지 않는다(잊은 비밀번호를 알 수 없음).
- **감사 로그:** 성공만 `AuditAction.PASSWORD_RESET`로 기록(요청·실패는 기록 안 함 — 계정 존재가 새고 무차별 대입 시 넘친다). `app/constants.py`의 `AuditAction`에 추가 + `web/src/lib/auditLogs.ts`의 `AUDIT_ACTION_LABEL`에 라벨 추가.
- 마이그레이션은 `uv run alembic revision --autogenerate`로 생성(현재 head `46cafcd5ae36`). `docs/schema.sql`도 함께 갱신(기존 규칙).
- **실행 환경:** 이 머신은 `python.exe` 직접 실행이 차단된다(`uv run ...` → os error 4551). **npm 스크립트를 거치면 정상.** 테스트는 `npm test`(Docker 데몬 필요 — testcontainers). 프론트 빌드는 `npm run build`.
- 커밋 메시지는 기존 스타일(한글, `feat:`/`fix:`/`test:`/`docs:` 접두사).

---

## File Structure

```
studio/
├─ app/
│  ├─ models/
│  │  ├─ password_reset_code.py      # 신규 (Task 1) — PasswordResetCode 테이블
│  │  └─ __init__.py                 # PasswordResetCode 재노출 (Task 1)
│  ├─ queries/
│  │  ├─ password_reset_codes.sql    # 신규 (Task 1) — insert/find/consume/increment
│  │  └─ users.sql                   # clear_lockout_after_reset 추가 (Task 3)
│  ├─ auth/
│  │  ├─ password_reset.py           # 신규 (Task 2) — generate/deliver 코드
│  │  └─ router.py                   # request/verify/confirm 엔드포인트 추가 (Task 2, 3)
│  └─ constants.py                   # AuditAction.PASSWORD_RESET 추가 (Task 3)
├─ alembic/versions/xxxx_*.py        # 신규 (Task 1) — autogenerate
├─ docs/schema.sql                   # password_reset_codes 반영 (Task 1)
├─ tests/
│  ├─ test_password_reset_code_model.py   # 신규 (Task 1)
│  ├─ test_password_reset_request.py      # 신규 (Task 2)
│  ├─ test_password_reset_verify.py       # 신규 (Task 3 — 실행 중 추가)
│  └─ test_password_reset_confirm.py      # 신규 (Task 3)
└─ web/src/
   ├─ components/PasswordResetModal.tsx   # 신규 (Task 4)
   ├─ pages/Login.tsx                     # "비밀번호를 잊으셨나요?" 링크 추가 (Task 4)
   └─ lib/auditLogs.ts                    # PASSWORD_RESET 라벨 (Task 3)
```

---

## Task 1: 재설정 코드 테이블 (모델 + 마이그레이션 + 쿼리)

**Files:**
- Create: `app/models/password_reset_code.py`, `app/queries/password_reset_codes.sql`, `tests/test_password_reset_code_model.py`
- Modify: `app/models/__init__.py`, `docs/schema.sql`
- Create: `alembic/versions/<autogen>_add_password_reset_codes.py`

**Interfaces:**
- Produces: `app.models.password_reset_code.PasswordResetCode` (테이블). 쿼리 이름: `insert_reset_code`(<!, id 반환), `find_active_reset_code`(^), `increment_reset_attempts`(!), `consume_reset_code`(!), `consume_active_reset_codes_for_user`(!). Task 2·3이 이 쿼리들을 쓴다.

- [x] **Step 1: 모델 테스트 작성**

`tests/test_password_reset_code_model.py`:

```python
from datetime import timedelta

from app.db import raw_connection
from app.models.user import User
from app.utils.time import now_local
from app.queries import queries


async def _make_user(db_session, email="reset-model@example.com") -> int:
    user = User(email=email, password_hash="x", name="테스트", role="MEMBER", status="ACTIVE")
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    return user.id


async def test_insert_and_find_active_reset_code(db_session):
    user_id = await _make_user(db_session)
    conn = await raw_connection(db_session)
    now = now_local()

    code_id = await queries.insert_reset_code(
        conn,
        user_id=user_id,
        code_hash="hashed-code",
        expires_at=now + timedelta(minutes=10),
        created_at=now,
        updated_at=now,
    )
    assert isinstance(code_id, int)

    row = await queries.find_active_reset_code(conn, user_id=user_id)
    assert row is not None
    assert row["code_hash"] == "hashed-code"
    assert row["attempts"] == 0
    assert row["consumed_at"] is None


async def test_consumed_code_is_not_active(db_session):
    user_id = await _make_user(db_session, "reset-model2@example.com")
    conn = await raw_connection(db_session)
    now = now_local()
    code_id = await queries.insert_reset_code(
        conn, user_id=user_id, code_hash="h", expires_at=now + timedelta(minutes=10),
        created_at=now, updated_at=now,
    )

    await queries.consume_reset_code(conn, id=code_id, consumed_at=now, updated_at=now)

    assert await queries.find_active_reset_code(conn, user_id=user_id) is None
```

- [x] **Step 2: 테스트 실패 확인**

Run: `npm test -- tests/test_password_reset_code_model.py`
Expected: FAIL — `PasswordResetCode` 모델·`password_reset_codes` 테이블·쿼리가 없어 수집/실행 단계에서 실패.

- [x] **Step 3: 모델 작성**

`app/models/password_reset_code.py` (`app/models/refresh_token.py`와 같은 구조):

```python
from datetime import datetime
from typing import Optional

from sqlalchemy import BigInteger
from sqlmodel import Field

from app.models.base import (
    BaseEntity,
    created_at_field,
    created_by_field,
    updated_at_field,
    updated_by_field,
)


class PasswordResetCode(BaseEntity, table=True):
    __tablename__ = "password_reset_codes"
    __table_args__ = {"comment": "비밀번호 재설정 인증코드 (해시 저장, 1회용, 만료)"}

    user_id: int = Field(
        sa_type=BigInteger,
        foreign_key="users.id",
        index=True,
        sa_column_kwargs={"comment": "코드 소유자 (FK: users.id)"},
    )
    code_hash: str = Field(
        index=True,
        sa_column_kwargs={"comment": "6자리 코드의 SHA-256 해시값 (원문 저장 안 함)"},
    )
    expires_at: datetime = Field(sa_column_kwargs={"comment": "만료 일시 (발급 + 10분)"})
    consumed_at: Optional[datetime] = Field(
        default=None,
        sa_column_kwargs={"comment": "사용 완료 일시 (1회용). NULL이면 미사용"},
    )
    attempts: int = Field(
        default=0,
        sa_column_kwargs={
            "server_default": "0",
            "comment": "검증 실패 누적. 한도 초과 시 코드 무효화",
        },
    )

    created_at: Optional[datetime] = created_at_field()
    created_by: Optional[int] = created_by_field()
    updated_at: Optional[datetime] = updated_at_field()
    updated_by: Optional[int] = updated_by_field()
```

`app/models/__init__.py`에 재노출 추가(기존 `RefreshToken` 옆에 같은 형식으로):

```python
from app.models.password_reset_code import PasswordResetCode  # noqa: F401
```

- [x] **Step 4: 쿼리 작성**

`app/queries/password_reset_codes.sql`:

```sql
-- name: insert_reset_code<!
INSERT INTO password_reset_codes (user_id, code_hash, expires_at, created_at, updated_at)
VALUES (:user_id, :code_hash, :expires_at, :created_at, :updated_at)
RETURNING id;

-- name: find_active_reset_code^
-- 해당 사용자의 미소비 코드 중 가장 최근 것 하나. 만료 여부는 앱에서 판단한다
-- (만료된 코드도 "틀림"과 같은 통일 응답을 줘야 하므로 조회 단계에서 거르지 않는다).
SELECT id, code_hash, expires_at, consumed_at, attempts
FROM password_reset_codes
WHERE user_id = :user_id AND consumed_at IS NULL
ORDER BY id DESC
LIMIT 1;

-- name: increment_reset_attempts!
UPDATE password_reset_codes
SET attempts = attempts + 1,
    updated_at = :updated_at
WHERE id = :id;

-- name: consume_reset_code!
UPDATE password_reset_codes
SET consumed_at = :consumed_at,
    updated_at = :updated_at
WHERE id = :id;

-- name: consume_active_reset_codes_for_user!
-- 새 코드 발급 전, 그 사용자의 미소비 코드를 모두 소비 처리해 활성 코드를 1개로 유지한다.
UPDATE password_reset_codes
SET consumed_at = :consumed_at,
    updated_at = :updated_at
WHERE user_id = :user_id AND consumed_at IS NULL;
```

> aiosql은 `app/queries/__init__.py`가 디렉토리를 로드하므로 새 `.sql` 파일은 자동 인식된다(별도 등록 불필요). 기존 파일들과 같은 위치에 두기만 하면 된다.

- [x] **Step 5: 마이그레이션 생성**

Run: `npm run migrate:make -- "add password reset codes"` 가 없다면 직접:
`uv run alembic revision --autogenerate -m "add password reset codes"` 를 npm으로 감싸 실행한다. 이 저장소에 마이그레이션 생성용 npm 스크립트가 없으면 `package.json`에 `"migrate:make": "uv run alembic revision --autogenerate -m"`를 추가한 뒤 위 명령을 쓴다.

생성된 파일이 `password_reset_codes` 테이블만 만드는지 확인한다(다른 테이블 변경이 섞이면 지운다). `down_revision`이 `46cafcd5ae36`인지 확인.

- [x] **Step 6: 마이그레이션 적용 + 테스트 통과 확인**

Run: `npm run migrate`
Expected: `Running upgrade 46cafcd5ae36 -> <new>, add password reset codes`

Run: `npm test -- tests/test_password_reset_code_model.py`
Expected: PASS (2개)

- [x] **Step 7: `docs/schema.sql` 갱신**

`refresh_tokens` 블록 아래에 `password_reset_codes`의 `CREATE TABLE` + `COMMENT ON` 을 같은 형식으로 추가한다(실제 컬럼: id, user_id, code_hash, expires_at, consumed_at, attempts, created_at/by, updated_at/by). 마이그레이션이 만든 실제 스키마와 일치시킨다.

- [x] **Step 8: 커밋**

```bash
git add app/models/password_reset_code.py app/models/__init__.py app/queries/password_reset_codes.sql alembic/versions docs/schema.sql tests/test_password_reset_code_model.py package.json
git commit -m "feat: 비밀번호 재설정 코드 테이블·모델·쿼리 추가"
```

---

## Task 2: 코드 생성·전달 + `POST /auth/password-reset/request`

**Files:**
- Create: `app/auth/password_reset.py`, `tests/test_password_reset_request.py`
- Modify: `app/auth/security.py`, `app/auth/router.py`

**Interfaces:**
- Consumes: Task 1의 쿼리들 · `app.auth.security` · `app.config.get_runtime_settings` 아님(여기선 불필요) · `app.queries.queries.find_by_email`
- Produces:
  - `app.auth.security.hash_reset_code(code: str) -> str` (SHA-256 hex, `hash_refresh_token`과 동일 방식)
  - `app.auth.password_reset.generate_reset_code() -> str` (6자리)
  - `app.auth.password_reset.deliver_reset_code(email: str, code: str) -> None` (지금은 로그 출력)
  - `app.auth.password_reset.RESET_CODE_TTL_MINUTES = 10`, `MAX_RESET_ATTEMPTS = 5`
  - `POST /auth/password-reset/request` — 항상 200 `{"message": "인증코드를 발송했습니다."}`. Task 3의 confirm이 이 코드를 검증한다.

- [x] **Step 1: 요청 엔드포인트 테스트 작성**

`tests/test_password_reset_request.py`:

```python
from app.auth.security import hash_reset_code
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

    resp = await client.post("/auth/password-reset/request", json={"email": "req-active@example.com"})
    assert resp.status_code == 200
    assert resp.json() == {"message": _MSG}

    conn = await raw_connection(db_session)
    user = await queries.find_by_email(conn, email="req-active@example.com")
    row = await queries.find_active_reset_code(conn, user_id=user["id"])
    assert row is not None
    # 원문이 아니라 해시로 저장된다.
    assert row["code_hash"] != "000000"
    assert len(row["code_hash"]) == 64  # sha256 hex


async def test_request_never_returns_the_code(client, db_session, caplog):
    await _make_user(db_session, "req-nocode@example.com")

    resp = await client.post("/auth/password-reset/request", json={"email": "req-nocode@example.com"})
    # 응답 본문 어디에도 6자리 숫자 코드가 없다(이 기능의 안전장치).
    import re
    assert not re.search(r"\b\d{6}\b", resp.text)


async def test_request_unknown_email_returns_same_message_and_stores_nothing(client, db_session):
    resp = await client.post("/auth/password-reset/request", json={"email": "nobody@example.com"})
    assert resp.status_code == 200
    assert resp.json() == {"message": _MSG}


async def test_request_disabled_account_gets_no_code_but_same_message(client, db_session):
    uid = await _make_user(db_session, "req-disabled@example.com", status="DISABLED")

    resp = await client.post("/auth/password-reset/request", json={"email": "req-disabled@example.com"})
    assert resp.status_code == 200
    assert resp.json() == {"message": _MSG}

    conn = await raw_connection(db_session)
    assert await queries.find_active_reset_code(conn, user_id=uid) is None


async def test_request_invalidates_previous_code(client, db_session):
    uid = await _make_user(db_session, "req-twice@example.com")
    conn = await raw_connection(db_session)

    await client.post("/auth/password-reset/request", json={"email": "req-twice@example.com"})
    first = await queries.find_active_reset_code(conn, user_id=uid)
    await client.post("/auth/password-reset/request", json={"email": "req-twice@example.com"})
    second = await queries.find_active_reset_code(conn, user_id=uid)

    # 활성 코드는 항상 최신 1개. 이전 코드는 무효화되어 최신 것과 다른 행이다.
    assert second["id"] != first["id"]
```

- [x] **Step 2: 테스트 실패 확인**

Run: `npm test -- tests/test_password_reset_request.py`
Expected: FAIL — `hash_reset_code`·엔드포인트가 없다.

- [x] **Step 3: `hash_reset_code` 추가**

`app/auth/security.py`에서 `hash_refresh_token` 근처에 추가(같은 SHA-256 방식):

```python
def hash_reset_code(code: str) -> str:
    """비밀번호 재설정 코드의 SHA-256 해시(hex). refresh 토큰과 같은 방식으로 원문을 저장하지 않는다."""
    return hashlib.sha256(code.encode()).hexdigest()
```

> `hash_refresh_token`이 이미 `hashlib.sha256(...).hexdigest()`를 쓰므로 `import hashlib`은 이미 있다. 없으면 추가한다.

- [x] **Step 4: `password_reset.py` 작성**

`app/auth/password_reset.py`:

```python
import logging
import secrets

logger = logging.getLogger("app.auth.password_reset")

RESET_CODE_TTL_MINUTES = 10
MAX_RESET_ATTEMPTS = 5


def generate_reset_code() -> str:
    """6자리 숫자 코드(000000~999999). secrets로 예측 불가하게 생성한다."""
    return f"{secrets.randbelow(1_000_000):06d}"


def deliver_reset_code(email: str, code: str) -> None:
    """인증코드를 사용자에게 전달한다.

    ⚠️ 이 함수가 이 기능의 유일한 보안 경계다. 지금은 서버 로그로만 전달하므로
    "코드를 아는 사람 = 서버 로그를 볼 수 있는 사람"이다. 운영 배포 전 반드시
    이 몸통을 '등록된 이메일함으로 코드를 보내는' 실제 이메일 발송으로 교체하고,
    아래 로그 출력을 제거해야 한다. 그 전까지 이 플로우는 개발용 뼈대다.
    """
    logger.info("[비밀번호 재설정] %s 코드: %s", email, code)
```

- [x] **Step 5: request 엔드포인트 구현**

`app/auth/router.py`에 추가(파일 상단 import에 `from datetime import timedelta`가 이미 있음; 없으면 추가). `password_reset` 모듈과 `hash_reset_code`, `UserStatus`를 import한다.

```python
from app.auth.password_reset import (
    RESET_CODE_TTL_MINUTES,
    deliver_reset_code,
    generate_reset_code,
)
from app.auth.security import hash_reset_code  # 기존 security import 줄에 병합해도 됨

_RESET_REQUEST_MESSAGE = "인증코드를 발송했습니다."
# 재설정 코드를 발급하는 상태. DISABLED/REJECTED는 되찾아도 로그인 못 하므로 발급하지 않는다.
_RESET_ALLOWED_STATUSES = (UserStatus.ACTIVE, UserStatus.PENDING)


class PasswordResetRequest(BaseModel):
    email: str


@router.post("/password-reset/request")
async def password_reset_request(body: PasswordResetRequest, db: AsyncSession = Depends(get_db)):
    email = body.email.strip().lower()
    conn = await raw_connection(db)
    row = await queries.find_by_email(conn, email=email)

    # 계정 존재/상태와 무관하게 응답은 항상 동일하다(계정 열거 방지).
    if row is not None and row["status"] in _RESET_ALLOWED_STATUSES:
        now = now_local()
        # 활성 코드는 사용자당 1개 — 새 코드 발급 전 이전 미소비 코드를 무효화한다.
        await queries.consume_active_reset_codes_for_user(
            conn, user_id=row["id"], consumed_at=now, updated_at=now
        )
        code = generate_reset_code()
        await queries.insert_reset_code(
            conn,
            user_id=row["id"],
            code_hash=hash_reset_code(code),
            expires_at=now + timedelta(minutes=RESET_CODE_TTL_MINUTES),
            created_at=now,
            updated_at=now,
        )
        await db.commit()
        # 커밋 이후에 전달한다 — 저장이 롤백됐는데 코드만 나가는 일이 없도록.
        deliver_reset_code(email, code)

    return {"message": _RESET_REQUEST_MESSAGE}
```

- [x] **Step 6: 테스트 통과 확인**

Run: `npm test -- tests/test_password_reset_request.py`
Expected: PASS (5개)

- [x] **Step 7: 커밋**

```bash
git add app/auth/password_reset.py app/auth/security.py app/auth/router.py tests/test_password_reset_request.py
git commit -m "feat: 비밀번호 재설정 코드 발급 API 추가 (POST /auth/password-reset/request)"
```

---

## Task 3: `POST /auth/password-reset/confirm` + 감사 로그

**Files:**
- Modify: `app/auth/router.py`, `app/queries/users.sql`, `app/constants.py`, `web/src/lib/auditLogs.ts`
- Create: `tests/test_password_reset_confirm.py`

**Interfaces:**
- Consumes: Task 1 쿼리 · Task 2의 `hash_reset_code`·`generate_reset_code`·`MAX_RESET_ATTEMPTS` · 기존 `queries.update_password`·`revoke_all_for_user`·`get_runtime_settings`·`audit.record`
- Produces: `POST /auth/password-reset/confirm`. `AuditAction.PASSWORD_RESET`. `users.sql`의 `clear_lockout_after_reset`.

- [x] **Step 1: confirm 테스트 작성**

`tests/test_password_reset_confirm.py`:

```python
from datetime import timedelta

from app.auth.security import hash_reset_code, verify_password
from app.constants import AuditAction
from app.db import raw_connection
from app.models.user import User
from app.queries import queries
from app.utils.time import now_local

_FAIL = "코드가 올바르지 않거나 만료되었습니다."


async def _user_with_code(db_session, email, code="123456", *, expired=False, status="ACTIVE"):
    user = User(email=email, password_hash="old-hash", name="테스트", role="MEMBER", status=status)
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)

    conn = await raw_connection(db_session)
    now = now_local()
    expires = now - timedelta(minutes=1) if expired else now + timedelta(minutes=10)
    code_id = await queries.insert_reset_code(
        conn, user_id=user.id, code_hash=hash_reset_code(code),
        expires_at=expires, created_at=now, updated_at=now,
    )
    await db_session.commit()
    return user.id, code_id


async def test_confirm_with_correct_code_changes_password(client, db_session):
    uid, _ = await _user_with_code(db_session, "conf-ok@example.com", code="654321")

    resp = await client.post("/auth/password-reset/confirm", json={
        "email": "conf-ok@example.com", "code": "654321", "new_password": "brand-new-pw",
    })
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
        conn, user_id=uid, token_hash="tok", expires_at=now + timedelta(days=1),
        created_at=now, updated_at=now,
    )
    await db_session.commit()

    await client.post("/auth/password-reset/confirm", json={
        "email": "conf-revoke@example.com", "code": "111111", "new_password": "another-new-pw",
    })

    row = await queries.find_by_token_hash(conn, token_hash="tok")
    assert row["revoked_at"] is not None


async def test_confirm_wrong_code_uniform_error_and_increments_attempts(client, db_session):
    uid, code_id = await _user_with_code(db_session, "conf-wrong@example.com", code="222222")

    resp = await client.post("/auth/password-reset/confirm", json={
        "email": "conf-wrong@example.com", "code": "000000", "new_password": "x-new-password",
    })
    assert resp.status_code == 400
    assert resp.json()["code"] == "INVALID_RESET_CODE"
    assert resp.json()["message"] == _FAIL

    conn = await raw_connection(db_session)
    row = await queries.find_active_reset_code(conn, user_id=uid)
    assert row["attempts"] == 1
    # 비밀번호는 그대로.
    assert verify_password("x-new-password", (await queries.find_by_id(conn, id=uid))["password_hash"]) is False


async def test_confirm_expired_code_uniform_error(client, db_session):
    await _user_with_code(db_session, "conf-exp@example.com", code="333333", expired=True)

    resp = await client.post("/auth/password-reset/confirm", json={
        "email": "conf-exp@example.com", "code": "333333", "new_password": "x-new-password",
    })
    assert resp.status_code == 400
    assert resp.json()["message"] == _FAIL


async def test_confirm_exhausted_attempts_invalidates_code(client, db_session):
    uid, _ = await _user_with_code(db_session, "conf-exhaust@example.com", code="444444")

    for _ in range(5):
        await client.post("/auth/password-reset/confirm", json={
            "email": "conf-exhaust@example.com", "code": "000000", "new_password": "x-new-password",
        })

    conn = await raw_connection(db_session)
    # 5회 실패로 코드가 무효화되어, 이후 올바른 코드도 거부된다.
    assert await queries.find_active_reset_code(conn, user_id=uid) is None
    resp = await client.post("/auth/password-reset/confirm", json={
        "email": "conf-exhaust@example.com", "code": "444444", "new_password": "x-new-password",
    })
    assert resp.status_code == 400


async def test_confirm_weak_password_rejected(client, db_session):
    await _user_with_code(db_session, "conf-weak@example.com", code="555555")

    resp = await client.post("/auth/password-reset/confirm", json={
        "email": "conf-weak@example.com", "code": "555555", "new_password": "short",
    })
    assert resp.status_code == 400
    assert resp.json()["code"] == "WEAK_PASSWORD"


async def test_confirm_unknown_email_uniform_error(client, db_session):
    resp = await client.post("/auth/password-reset/confirm", json={
        "email": "ghost@example.com", "code": "123456", "new_password": "x-new-password",
    })
    assert resp.status_code == 400
    assert resp.json()["message"] == _FAIL


async def test_confirm_records_audit_on_success(client, db_session):
    uid, _ = await _user_with_code(db_session, "conf-audit@example.com", code="666666")

    await client.post("/auth/password-reset/confirm", json={
        "email": "conf-audit@example.com", "code": "666666", "new_password": "audited-new-pw",
    })

    conn = await raw_connection(db_session)
    # 기존 감사 테스트(test_core_audit.py)와 같은 raw SELECT 방식으로 마지막 행을 확인한다.
    action = await conn.fetchval(
        "SELECT action FROM audit_logs WHERE actor_id = $1 ORDER BY id DESC LIMIT 1", uid
    )
    assert action == AuditAction.PASSWORD_RESET
```

- [x] **Step 2: 테스트 실패 확인**

Run: `npm test -- tests/test_password_reset_confirm.py`
Expected: FAIL — confirm 엔드포인트·`PASSWORD_RESET`·`clear_lockout_after_reset`가 없다.

- [x] **Step 3: `AuditAction.PASSWORD_RESET` 추가**

`app/constants.py`의 `AuditAction` "인증" 섹션(`PASSWORD_CHANGE` 아래)에 추가:

```python
    PASSWORD_RESET = "PASSWORD_RESET"
```

`web/src/lib/auditLogs.ts`의 `AUDIT_ACTION_LABEL`에 라벨 추가(기존 항목과 같은 형식):

```ts
  PASSWORD_RESET: '비밀번호 재설정',
```

- [x] **Step 4: 잠금 해제 쿼리 추가**

`app/queries/users.sql`에 추가:

```sql
-- name: clear_lockout_after_reset!
-- 비밀번호 재설정 성공 시 잠금·실패 횟수를 함께 푼다. 비밀번호를 잊어 연속 실패로
-- 잠긴 계정이 재설정의 흔한 대상이라, 재설정 직후 바로 로그인할 수 있어야 한다.
UPDATE users
SET failed_login_count = 0,
    locked_at = NULL,
    updated_at = :updated_at
WHERE id = :id;
```

- [x] **Step 5: confirm 엔드포인트 구현**

`app/auth/router.py`에 추가. `MAX_RESET_ATTEMPTS`를 import에 추가하고, `hash_password`·`verify_password`가 이미 import돼 있음을 확인.

```python
from app.auth.password_reset import MAX_RESET_ATTEMPTS  # Task 2 import 줄에 병합


class PasswordResetConfirm(BaseModel):
    email: str
    code: str
    new_password: str


@router.post("/password-reset/confirm")
async def password_reset_confirm(
    body: PasswordResetConfirm, request: Request, db: AsyncSession = Depends(get_db)
):
    # 실패는 원인 불문 같은 400으로 응답한다(계정 존재·코드 상태를 흘리지 않는다).
    invalid = AppError(400, "INVALID_RESET_CODE", "코드가 올바르지 않거나 만료되었습니다.")

    email = body.email.strip().lower()
    conn = await raw_connection(db)
    user = await queries.find_by_email(conn, email=email)
    if user is None:
        raise invalid

    code_row = await queries.find_active_reset_code(conn, user_id=user["id"])
    if code_row is None:
        raise invalid

    now = now_local()
    if code_row["expires_at"] < now:
        raise invalid

    # 코드가 틀린 경우에만 시도 횟수를 올린다(정책 미달 재시도로 시도가 소진되지 않게).
    if not hmac.compare_digest(code_row["code_hash"], hash_reset_code(body.code)):
        await queries.increment_reset_attempts(conn, id=code_row["id"], updated_at=now)
        # code_row["attempts"]는 증가 전 값 — 이번 실패까지 더하면 +1이다. 한도 도달 시 무효화.
        if code_row["attempts"] + 1 >= MAX_RESET_ATTEMPTS:
            await queries.consume_reset_code(conn, id=code_row["id"], consumed_at=now, updated_at=now)
        await db.commit()
        raise invalid

    # 코드 일치 — 비밀번호 정책 검증 후 변경. 정책 미달이면 코드를 그대로 두어(소비·증가 없음)
    # 더 긴 비밀번호로 곧바로 다시 시도할 수 있게 한다.
    min_len = (await get_runtime_settings(conn)).password_min_len
    if len(body.new_password) < min_len:
        raise AppError(400, "WEAK_PASSWORD", f"새 비밀번호는 {min_len}자 이상이어야 합니다.")

    await queries.update_password(
        conn, id=user["id"], password_hash=hash_password(body.new_password),
        updated_at=now, updated_by=user["id"],
    )
    await queries.consume_reset_code(conn, id=code_row["id"], consumed_at=now, updated_at=now)
    await queries.clear_lockout_after_reset(conn, id=user["id"], updated_at=now)
    await queries.revoke_all_for_user(conn, user_id=user["id"], revoked_at=now, updated_at=now)
    await audit.record(
        conn,
        action=AuditAction.PASSWORD_RESET,
        request=request,
        actor=user,
        target_type=AuditTarget.USER,
        target_id=user["id"],
        target_label=user["name"],
        summary="비밀번호 재설정 — 코드 인증, 전 세션 폐기",
    )
    await db.commit()
    return {"status": "ok"}
```

> import 확인: `hmac`(표준 라이브러리), `AppError`, `AuditAction`, `AuditTarget`, `audit`, `get_runtime_settings`, `hash_password`가 `router.py`에 있는지 보고 없는 것만 추가한다. `hmac.compare_digest`는 SHA-256 hex 문자열 비교에 상수시간을 보장한다.

- [x] **Step 6: 테스트 통과 확인**

Run: `npm test -- tests/test_password_reset_confirm.py`
Expected: PASS (8개)

- [x] **Step 7: 전체 백엔드 회귀 + 커밋**

Run: `npm test`
Expected: 전체 통과(신규 15개 포함).

```bash
git add app/auth/router.py app/queries/users.sql app/constants.py web/src/lib/auditLogs.ts tests/test_password_reset_confirm.py
git commit -m "feat: 비밀번호 재설정 확인 API 추가 (POST /auth/password-reset/confirm)"
```

---

## Task 4: 프론트 — 재설정 팝업 + 로그인 화면 링크

**Files:**
- Create: `web/src/components/PasswordResetModal.tsx`
- Modify: `web/src/pages/Login.tsx`

**Interfaces:**
- Consumes: 기존 `Modal`·`TextField`·`Button`·`FormError` · `api`(`api.post`) · `ApiError` · `usePasswordMinLen`(`web/src/lib/policy`) · 백엔드 `POST /auth/password-reset/request`·`confirm`

- [x] **Step 1: 팝업 컴포넌트 작성**

`web/src/components/PasswordResetModal.tsx` (2단계 상태):

```tsx
import { useState, type FormEvent } from 'react'
import { Button } from './Button'
import { FormError } from './FormError'
import { Modal } from './Modal'
import { TextField } from './TextField'
import { api, ApiError } from '../lib/api'
import { usePasswordMinLen } from '../lib/policy'

export function PasswordResetModal({ onClose, onDone }: { onClose: () => void; onDone: (msg: string) => void }) {
  const passwordMinLen = usePasswordMinLen()
  const [step, setStep] = useState<'email' | 'code'>('email')
  const [email, setEmail] = useState('')
  const [code, setCode] = useState('')
  const [next, setNext] = useState('')
  const [confirm, setConfirm] = useState('')
  const [error, setError] = useState<string>()
  const [pending, setPending] = useState(false)

  async function requestCode(event: FormEvent) {
    event.preventDefault()
    setError(undefined)
    setPending(true)
    try {
      await api.post('/auth/password-reset/request', { email })
      setStep('code')
    } catch (e) {
      setError(e instanceof ApiError ? e.message : '알 수 없는 오류가 발생했습니다.')
    } finally {
      setPending(false)
    }
  }

  async function confirmReset(event: FormEvent) {
    event.preventDefault()
    setError(undefined)
    if (next.length < passwordMinLen) {
      setError(`새 비밀번호는 ${passwordMinLen}자 이상이어야 합니다.`)
      return
    }
    if (next !== confirm) {
      setError('새 비밀번호가 일치하지 않습니다.')
      return
    }
    setPending(true)
    try {
      await api.post('/auth/password-reset/confirm', { email, code, new_password: next })
      onDone('비밀번호가 변경되었습니다. 새 비밀번호로 로그인하세요.')
    } catch (e) {
      setError(e instanceof ApiError ? e.message : '알 수 없는 오류가 발생했습니다.')
    } finally {
      setPending(false)
    }
  }

  return (
    <Modal title="비밀번호 재설정" onClose={onClose}>
      {step === 'email' ? (
        <form onSubmit={requestCode} className="space-y-4">
          <FormError message={error} />
          <TextField
            id="reset-email" label="이메일" type="email" autoComplete="email" required
            value={email} onChange={(e) => setEmail(e.target.value)}
          />
          <Button type="submit" pending={pending}>인증코드 받기</Button>
        </form>
      ) : (
        <form onSubmit={confirmReset} className="space-y-4">
          <p className="rounded-md bg-surface-muted px-4 py-2 text-sm text-fg-muted">
            인증코드를 발송했습니다. 개발 중에는 <strong>서버 로그</strong>에서 코드를 확인하세요.
          </p>
          <FormError message={error} />
          <TextField
            id="reset-code" label="인증코드(6자리)" inputMode="numeric" required
            value={code} onChange={(e) => setCode(e.target.value)}
          />
          <TextField
            id="reset-new" label="새 비밀번호" type="password" autoComplete="new-password" required
            value={next} onChange={(e) => setNext(e.target.value)}
          />
          <TextField
            id="reset-confirm" label="새 비밀번호 확인" type="password" autoComplete="new-password" required
            value={confirm} onChange={(e) => setConfirm(e.target.value)}
          />
          <Button type="submit" pending={pending}>비밀번호 변경</Button>
        </form>
      )}
    </Modal>
  )
}
```

> `TextField`의 실제 props(특히 `inputMode` 허용 여부)를 `web/src/components/TextField.tsx`에서 확인하고, 지원하지 않는 속성이면 뺀다. `usePasswordMinLen`의 정확한 이름·반환도 `web/src/lib/policy.ts`에서 확인해 맞춘다.

- [x] **Step 2: 로그인 화면에 링크 연결**

`web/src/pages/Login.tsx`에서 상단에 `useState`로 팝업 표시 상태와 `PasswordResetModal` import를 추가하고, "회원가입" 링크 문단 아래에 "비밀번호를 잊으셨나요?" 버튼을 넣는다. 성공 시 팝업의 `onDone` 메시지를 로그인 폼 상단 `notice` 자리에 표시한다(기존 `notice` 상태를 재사용하거나 별도 상태 추가).

구체적으로: `const [showReset, setShowReset] = useState(false)`, `const [resetNotice, setResetNotice] = useState<string>()` 추가. 폼 상단 `notice` 렌더 조건을 `notice || resetNotice`로 확장. 하단에:

```tsx
      <p className="mt-2 text-center text-sm text-fg-muted">
        <button type="button" onClick={() => setShowReset(true)} className="font-medium text-fg underline">
          비밀번호를 잊으셨나요?
        </button>
      </p>
      {showReset && (
        <PasswordResetModal
          onClose={() => setShowReset(false)}
          onDone={(msg) => { setShowReset(false); setResetNotice(msg) }}
        />
      )}
```

- [x] **Step 3: 빌드 확인**

Run: `npm run build`
Expected: TypeScript 컴파일 통과, 에러 없음.

- [x] **Step 4: 수동 워크스루**

`npm run dev`로 띄운 뒤(백엔드·프론트):
1. 로그인 화면 → "비밀번호를 잊으셨나요?" → 팝업.
2. 승인된 샘플 계정 이메일(`sample-member1@example.com` 등) 입력 → 인증코드 받기.
3. **`password_reset_codes` 테이블에서 코드 확인** — `SELECT code FROM password_reset_codes ORDER BY id DESC LIMIT 1;`
4. 그 코드 입력 → 인증코드 확인(2단계) → 새 비밀번호(정책 길이 이상) 입력 → 비밀번호 변경(3단계).
5. 팝업 닫히고 로그인 화면에 "비밀번호가 변경되었습니다" 안내.
6. 새 비밀번호로 로그인 성공.
7. (원복) 그 샘플 계정 비밀번호를 원래대로 되돌리거나 다시 시드한다.

- [x] **Step 5: 커밋**

```bash
git add web/src/components/PasswordResetModal.tsx web/src/pages/Login.tsx
git commit -m "feat: 로그인 화면에 비밀번호 재설정 팝업 추가"
```

---

## 완료 조건

- `npm test` 전체 통과(신규 백엔드 테스트 15개 포함)
- `npm run build` 통과
- 수동 워크스루(Task 4 Step 4)의 6단계가 브라우저에서 동작
- `docs/schema.sql`에 `password_reset_codes`가 반영됨
- API 응답 어디에도 6자리 코드가 노출되지 않음(Task 2 Step 1 테스트로 고정)

## 다음 단계 (이번 범위 밖)

- `deliver_reset_code()`를 실제 이메일 발송으로 교체 → 설계 0장의 보안 경고 해소. (콘솔 출력은 애초에 넣지 않았으므로 빈 몸통을 채우기만 하면 된다.)
- 요청 rate limit(한 이메일에 대한 발송 빈도 제한).
