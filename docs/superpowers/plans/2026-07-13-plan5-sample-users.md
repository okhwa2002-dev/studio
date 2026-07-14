# Studio — Plan 5: 개발용 사용자 샘플 데이터 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 가입 승인 화면 개발에 쓸 샘플 사용자 8명(PENDING 5 · ACTIVE 2 · REJECTED 1)을 멱등하게 생성하는 시드를 만든다.

**Architecture:** 기존 `seed_admin`과 같은 2단 구조 — 핵심 로직(`app/auth/seed_sample_users.py`, raw 커넥션을 인자로 받아 테스트 가능)과 CLI 진입점(`scripts/seed_sample_users.py`). 고정된 이메일로 존재 여부를 확인해 멱등성을 얻고, `DATABASE_URL`의 호스트명을 파싱해 로컬 DB에서만 실행되게 막는다.

**Tech Stack:** 기존 그대로 — Python 3.12, aiosql(`app/queries/users.sql`), argon2(`app/auth/security.py`), pytest+testcontainers.

**설계 문서:** `docs/superpowers/specs/2026-07-13-sample-users-design.md`

## Global Constraints

- **선행 조건: Plan 4(공통코드 대문자화)가 먼저 적용되어 있어야 한다.** 이 시드는 `app/constants.py`의 `UserRole`·`UserStatus`(대문자 StrEnum)를 import해서 쓴다. `app/constants.py`가 없으면 이 Plan을 시작하지 말고 보고하라.
- 코드값 리터럴(`"pending"`, `"PENDING"`)을 쓰지 않는다. 항상 `UserStatus.PENDING` 같은 Enum 멤버를 쓴다.
- 샘플 계정의 비밀번호는 **`password123`** 이며 소스에 상수로 둔다.
- 샘플 이메일은 **고정**이다. 이것이 멱등성의 근거다 — 랜덤 생성하지 않는다.
- **로컬 DB에서만 실행된다.** `DATABASE_URL`의 호스트가 `localhost`/`127.0.0.1`이 아니면 아무것도 하지 않는다. 판별은 반드시 **호스트명 파싱**으로 한다 — 문자열 포함 검사(`"localhost" in url`)는 `db.localhost.evil.com`에 속는다.
- 개수를 인자로 받는 옵션(`--pending 12`), 샘플 삭제 명령, 대량 데이터 생성은 **만들지 않는다**(YAGNI).
- 커밋은 각 Task 마지막 단계에서 수행하며, 기존 스타일(한글, `기능:`/`수정:`/`변경:` 접두사)을 따른다.

### 실행 환경 주의 (중요)

이 머신은 **Windows 애플리케이션 제어 정책이 `python.exe` 직접 실행을 차단**한다. 셸에서 `uv run pytest` / `uv run python ...`을 직접 실행하면 `os error 4551`로 실패한다. **npm 스크립트를 거치면 정상 실행된다.**

| 하려는 것 | 쓸 명령 |
|-----------|---------|
| 백엔드 테스트 | `npm test` |
| 샘플 시드 실행 | `npm run seed:sample` (Task 2에서 이 스크립트를 추가한다) |

pytest는 Docker 데몬이 떠 있어야 한다(testcontainers가 임시 Postgres를 띄운다).

---

## File Structure

```
studio/
├─ app/auth/seed_sample_users.py       # 신규 (Task 1) — 핵심 로직: 샘플 목록·멱등 생성·로컬 DB 판별
├─ scripts/seed_sample_users.py        # 신규 (Task 2) — CLI 진입점
├─ tests/test_seed_sample_users.py     # 신규 (Task 1)
├─ package.json                        # seed:admin / seed:sample 스크립트 추가 (Task 2)
└─ README.md                           # 시드 실행 방법을 npm 기준으로 갱신 (Task 2)
```

`app/auth/seed_sample_users.py`는 raw asyncpg 커넥션을 인자로 받는다 — 세션·설정을 스스로 만들지 않으므로 테스트에서 그대로 호출된다. 설정 로드·세션 생성·출력은 전부 `scripts/` 쪽 책임이다. 이것이 기존 `seed_admin`의 구조이며 그대로 따른다.

---

## Task 1: 시드 핵심 로직 + 테스트

**Files:**
- Create: `app/auth/seed_sample_users.py`
- Test: `tests/test_seed_sample_users.py`

**Interfaces:**
- Consumes: `app.constants.UserRole` / `app.constants.UserStatus` (Plan 4) · `app.auth.security.hash_password(password: str) -> str` · `app.queries.queries.find_by_email(conn, email=...)` / `insert_user(conn, email=, password_hash=, role=, status=, created_at=, updated_at=)` / `list_by_status(conn, status=...)` (async 이터레이터) · `app.utils.time.now_local()`
- Produces:
  - `SAMPLE_PASSWORD: str` = `"password123"`
  - `SAMPLE_USERS: list[tuple[str, UserRole, UserStatus]]` — 8개 항목
  - `def is_local_database(database_url: str) -> bool`
  - `async def ensure_sample_users_seeded(conn) -> int` — 생성한 계정 수를 반환
  - Task 2의 CLI가 이 네 가지를 그대로 import한다.

- [ ] **Step 1: 실패하는 테스트 작성**

`tests/test_seed_sample_users.py` 생성:

```python
from app.auth.seed_sample_users import (
    SAMPLE_PASSWORD,
    SAMPLE_USERS,
    ensure_sample_users_seeded,
    is_local_database,
)
from app.constants import UserStatus
from app.db import raw_connection
from app.queries import queries


async def _count_by_status(conn, status: UserStatus) -> int:
    return len([row async for row in queries.list_by_status(conn, status=status)])


async def test_seeds_eight_sample_users(db_session):
    conn = await raw_connection(db_session)

    created = await ensure_sample_users_seeded(conn)
    assert created == 8

    assert await _count_by_status(conn, UserStatus.PENDING) == 5
    assert await _count_by_status(conn, UserStatus.ACTIVE) == 2
    assert await _count_by_status(conn, UserStatus.REJECTED) == 1


async def test_seeding_is_idempotent(db_session):
    conn = await raw_connection(db_session)

    first = await ensure_sample_users_seeded(conn)
    second = await ensure_sample_users_seeded(conn)

    assert first == len(SAMPLE_USERS)
    assert second == 0


async def test_active_sample_user_can_log_in(client, db_session):
    # 소스에 적힌 비밀번호가 실제로 로그인에 통하는지 확인한다.
    # (해시를 잘못 만들면 시드는 성공하지만 아무도 로그인하지 못한다.)
    conn = await raw_connection(db_session)
    await ensure_sample_users_seeded(conn)
    await db_session.commit()

    resp = await client.post(
        "/auth/login",
        json={"email": "sample-member1@example.com", "password": SAMPLE_PASSWORD},
    )
    assert resp.status_code == 200


async def test_pending_sample_user_cannot_log_in(client, db_session):
    conn = await raw_connection(db_session)
    await ensure_sample_users_seeded(conn)
    await db_session.commit()

    resp = await client.post(
        "/auth/login",
        json={"email": "sample-pending1@example.com", "password": SAMPLE_PASSWORD},
    )
    assert resp.status_code == 403


def test_is_local_database_accepts_local_hosts():
    assert is_local_database("postgresql+asyncpg://studio:studio@localhost:5437/studio") is True
    assert is_local_database("postgresql+asyncpg://studio:studio@127.0.0.1:5437/studio") is True


def test_is_local_database_rejects_remote_hosts():
    assert is_local_database("postgresql+asyncpg://studio:studio@db.example.com:5432/studio") is False
    # 문자열 포함 검사("localhost" in url)로 구현하면 아래에서 걸린다 — 호스트명을 파싱해야 한다.
    assert is_local_database("postgresql+asyncpg://studio:studio@db.localhost.evil.com:5432/studio") is False
```

- [ ] **Step 2: 테스트가 실패하는지 확인 (RED)**

Run: `npm test`
Expected: FAIL — `app/auth/seed_sample_users.py`가 없어 `ModuleNotFoundError: No module named 'app.auth.seed_sample_users'` 로 수집 단계에서 실패한다.

- [ ] **Step 3: 시드 로직 구현**

`app/auth/seed_sample_users.py` 생성:

```python
from urllib.parse import urlsplit

from app.auth.security import hash_password
from app.constants import UserRole, UserStatus
from app.queries import queries
from app.utils.time import now_local

SAMPLE_PASSWORD = "password123"

# 이메일이 고정이라는 점이 멱등성의 근거다. 이미 있는 이메일은 건너뛰므로
# 몇 번을 돌려도 중복이 생기지 않고, 승인해 둔 샘플 계정의 상태도 되돌아가지 않는다.
SAMPLE_USERS: list[tuple[str, UserRole, UserStatus]] = [
    ("sample-pending1@example.com", UserRole.MEMBER, UserStatus.PENDING),
    ("sample-pending2@example.com", UserRole.MEMBER, UserStatus.PENDING),
    ("sample-pending3@example.com", UserRole.MEMBER, UserStatus.PENDING),
    ("sample-pending4@example.com", UserRole.MEMBER, UserStatus.PENDING),
    ("sample-pending5@example.com", UserRole.MEMBER, UserStatus.PENDING),
    ("sample-member1@example.com", UserRole.MEMBER, UserStatus.ACTIVE),
    ("sample-member2@example.com", UserRole.MEMBER, UserStatus.ACTIVE),
    ("sample-rejected1@example.com", UserRole.MEMBER, UserStatus.REJECTED),
]


def is_local_database(database_url: str) -> bool:
    """DATABASE_URL이 로컬 호스트를 가리키는지 판별한다.

    문자열 포함 검사(`"localhost" in url`)는 db.localhost.evil.com 같은 주소에 속는다.
    반드시 호스트명을 파싱해서 비교한다.
    """
    host = urlsplit(database_url).hostname
    return host in ("localhost", "127.0.0.1")


async def ensure_sample_users_seeded(conn) -> int:
    """샘플 사용자를 생성하고 생성한 개수를 반환한다.

    이미 존재하는 이메일은 건너뛴다(재실행해도 안전).
    """
    now = now_local()
    # 8명이 같은 비밀번호를 쓰므로 해시는 한 번만 계산한다(argon2는 의도적으로 느리다).
    password_hash = hash_password(SAMPLE_PASSWORD)

    created = 0
    for email, role, status in SAMPLE_USERS:
        if await queries.find_by_email(conn, email=email) is not None:
            continue
        await queries.insert_user(
            conn,
            email=email,
            password_hash=password_hash,
            role=role,
            status=status,
            created_at=now,
            updated_at=now,
        )
        created += 1

    return created
```

- [ ] **Step 4: 테스트 통과 확인 (GREEN)**

Run: `npm test`
Expected: PASS — 기존 테스트 + 신규 6개가 모두 통과한다.

- [ ] **Step 5: 커밋**

```bash
git add app/auth/seed_sample_users.py tests/test_seed_sample_users.py
git commit -m "기능: 개발용 사용자 샘플 시드 로직 추가 (멱등, 로컬 DB 전용)"
```

---

## Task 2: CLI 진입점 + npm 스크립트 + README

**Files:**
- Create: `scripts/seed_sample_users.py`
- Modify: `package.json`, `README.md`

**Interfaces:**
- Consumes: Task 1의 `SAMPLE_PASSWORD`, `SAMPLE_USERS`, `ensure_sample_users_seeded(conn) -> int`, `is_local_database(database_url) -> bool` · 기존 `app.config.get_settings()` · `app.db.async_session_maker` / `raw_connection(session)`
- Produces: `npm run seed:sample` (샘플 8명) · `npm run seed:admin` (기존 관리자 시드)

- [ ] **Step 1: CLI 진입점 작성**

`scripts/seed_sample_users.py` 생성 (기존 `scripts/seed_admin.py`와 같은 형태):

```python
import asyncio

from app.auth.seed_sample_users import (
    SAMPLE_PASSWORD,
    SAMPLE_USERS,
    ensure_sample_users_seeded,
    is_local_database,
)
from app.config import get_settings
from app.db import async_session_maker, raw_connection


async def main() -> None:
    settings = get_settings()

    # 이 스크립트는 비밀번호가 소스에 적힌, 로그인 가능한 계정을 만든다.
    # 운영 DB에 붙은 채 실행되면 그대로 백도어가 되므로 로컬에서만 동작시킨다.
    if not is_local_database(settings.database_url):
        print("로컬 DB가 아닙니다. 샘플 데이터는 로컬에서만 생성할 수 있습니다.")
        return

    async with async_session_maker() as session:
        conn = await raw_connection(session)
        created = await ensure_sample_users_seeded(conn)
        await session.commit()

    if created == 0:
        print("이미 존재하는 샘플 사용자입니다. 새로 생성한 계정이 없습니다.")
        return

    print(f"샘플 사용자 {created}명을 생성했습니다. (전체 {len(SAMPLE_USERS)}명)")
    print(f"비밀번호는 모두 {SAMPLE_PASSWORD} 입니다.")


if __name__ == "__main__":
    asyncio.run(main())
```

- [ ] **Step 2: npm 스크립트 추가**

루트 `package.json`의 `scripts`에 두 줄을 추가한다(기존 항목은 그대로 둔다):

```json
    "seed:admin": "uv run python scripts/seed_admin.py",
    "seed:sample": "uv run python scripts/seed_sample_users.py",
```

- [ ] **Step 3: 실제로 실행해 확인**

DB가 떠 있어야 한다(`docker compose up -d db`, 마이그레이션 적용 완료 상태).

Run: `npm run seed:sample`
Expected:
```
샘플 사용자 8명을 생성했습니다. (전체 8명)
비밀번호는 모두 password123 입니다.
```

- [ ] **Step 4: 멱등성 확인 — 한 번 더 실행**

Run: `npm run seed:sample`
Expected:
```
이미 존재하는 샘플 사용자입니다. 새로 생성한 계정이 없습니다.
```

- [ ] **Step 5: DB에 실제로 들어갔는지 확인**

Run: `docker compose exec -T db psql -U studio -d studio -c "SELECT email, role, status FROM users ORDER BY id;"`
Expected: 기존 관리자 1명 + 샘플 8명. 샘플의 `role`은 모두 `MEMBER`, `status`는 `PENDING` 5개 · `ACTIVE` 2개 · `REJECTED` 1개. 소문자 값이 하나도 없다.

- [ ] **Step 6: README 갱신**

`README.md`의 "### 최초 1회만" 블록에서 관리자 시드 줄을 npm 명령으로 바꾸고, 샘플 시드를 추가한다. 아래 줄을

```
uv run python scripts/seed_admin.py      # 최초 관리자 계정 (.env의 ADMIN_EMAIL/ADMIN_PASSWORD)
```

이렇게 바꾼다:

```
npm run seed:admin                       # 최초 관리자 계정 (.env의 ADMIN_EMAIL/ADMIN_PASSWORD)
npm run seed:sample                      # (선택) 개발용 샘플 사용자 8명 — 비밀번호는 모두 password123
```

그리고 명령 표에 두 줄을 추가한다:

| `npm run seed:admin` | 최초 관리자 계정 생성 |
| `npm run seed:sample` | 개발용 샘플 사용자 8명 (로컬 DB에서만 동작) |

- [ ] **Step 7: 커밋**

```bash
git add scripts/seed_sample_users.py package.json README.md
git commit -m "기능: 샘플 사용자 시드 CLI와 npm 스크립트 추가 (npm run seed:sample)"
```

---

## 완료 조건

- `npm test` 통과 (Task 1의 신규 6개 포함)
- `npm run seed:sample`이 8명을 생성하고, 재실행 시 0명을 생성한다
- DB에 샘플 8명이 대문자 코드값으로 들어가 있다
- `sample-member1@example.com` / `password123` 으로 실제 로그인이 되고, `sample-pending1@example.com`은 403으로 막힌다

## 다음 작업 (이번 범위 밖)

- `/admin/approvals` 화면 — 이 샘플 데이터가 그 화면의 개발·확인 재료가 된다
