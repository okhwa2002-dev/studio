# Studio — Plan 4: 공통코드 값 대문자 통일 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** DB에 저장되는 공통코드 값(`users.role`, `users.status`)을 대문자로 통일하고, 12개 파일에 흩어진 문자열 리터럴을 `app/constants.py`의 Enum 한 곳으로 모은다.

**Architecture:** Python 3.12의 `StrEnum`으로 `UserRole`/`UserStatus`를 정의하고, 백엔드·API·프론트가 모두 같은 대문자 값을 쓴다(경계 변환 계층 없음). 기존 DB 데이터는 Alembic 리비전 하나로 `upper()` 변환한다. 스키마 문서는 `docs/schema.sql` 하나로 일원화한다(`docs/SCHEMA.md` 삭제).

**Tech Stack:** 기존 그대로 — Python 3.12, FastAPI, SQLModel(스키마 정의용), aiosql(쿼리), Alembic, pytest+testcontainers / 프론트 React+TypeScript.

**설계 문서:** `docs/superpowers/specs/2026-07-13-uppercase-codes-design.md`

## Global Constraints

- 코드값은 **대문자**: `role` = `MEMBER` | `ADMIN`, `status` = `PENDING` | `ACTIVE` | `DISABLED` | `REJECTED`.
- 값의 정의는 **`app/constants.py` 한 곳**. 백엔드 코드·테스트는 리터럴(`"active"`, `"ADMIN"`)을 쓰지 않고 Enum 멤버(`UserStatus.ACTIVE`)를 쓴다. 프론트는 TypeScript 유니온 타입으로 같은 값을 표현한다.
- **경계 변환 계층을 만들지 않는다.** DB 저장값 · API 응답 · API 쿼리 파라미터 · 프론트 타입이 전부 같은 대문자 값이다.
- **DB CHECK 제약을 걸지 않는다.** 값 추가마다 마이그레이션이 필요해진다. 검증은 앱 경계(FastAPI의 Enum 검증)에서 한다.
- **공통코드 테이블(코드 마스터)을 만들지 않는다.** 값의 출처는 소스 코드다(상위 설계가 에러 코드를 DB로 관리하지 않기로 한 것과 같은 이유).
- 화면의 한글 라벨링(`ADMIN` → "관리자")은 **이번 범위가 아니다.** 대시보드는 `user.role`을 그대로 출력한다.
- 마이그레이션은 **스키마를 바꾸지 않는다.** `role`/`status`의 기본값은 DB가 아니라 앱 계층(`Field(default=...)`)에 있으므로, 바꿀 것은 **데이터와 컬럼 코멘트뿐**이다.
- **스키마 문서 갱신은 마이그레이션과 같은 커밋에서** 한다. 먼저 고치면 문서가 실제 DB와 어긋나는 기간이 생긴다.
- 커밋은 각 Task 마지막 단계에서 수행하며, 기존 스타일(한글, `기능:`/`수정:`/`변경:`/`정리:` 접두사)을 따른다.

### 실행 환경 주의 (중요)

이 머신은 **Windows 애플리케이션 제어 정책이 `python.exe` 직접 실행을 차단**한다. 셸에서 `uv run pytest` / `uv run alembic`을 직접 실행하면 `os error 4551`로 실패한다. **npm 스크립트를 거치면 정상 실행된다.**

| 하려는 것 | 쓸 명령 |
|-----------|---------|
| 백엔드 테스트 | `npm test` (= `uv run pytest`) |
| 마이그레이션 적용 | `npm run migrate` (Task 2에서 이 스크립트를 추가한다) |
| 프론트 빌드 | `npm run build` |

pytest는 Docker 데몬이 떠 있어야 한다(testcontainers가 임시 Postgres를 띄운다).

---

## File Structure

```
studio/
├─ app/
│  ├─ constants.py                 # 신규 (Task 1) — UserRole, UserStatus (StrEnum)
│  ├─ models/user.py               # 기본값·컬럼 코멘트 (Task 1)
│  └─ auth/
│     ├─ router.py                 # 가입/로그인/갱신 (Task 1)
│     ├─ dependencies.py           # current_user / require_admin (Task 1)
│     ├─ admin_router.py           # 승인/거절 + status 쿼리 파라미터 (Task 1)
│     └─ seed_admin.py             # 최초 admin 시드 (Task 1)
├─ tests/                          # 리터럴 → Enum 상수 (Task 1), 422 테스트 추가 (Task 1)
├─ alembic/versions/
│  └─ c9f2a17b4d31_uppercase_user_code_values.py   # 신규 (Task 2)
├─ docs/
│  ├─ schema.sql                   # 코멘트 대문자화 + SCHEMA.md 내용 흡수 (Task 2)
│  └─ SCHEMA.md                    # 삭제 (Task 2)
├─ package.json                    # migrate 스크립트 추가 (Task 2)
└─ web/src/lib/auth.tsx            # User.role 타입 대문자 (Task 3)
```

`app/constants.py`는 아무것도 import하지 않는다 — 모델·라우터·의존성·시드·테스트 어디서 가져다 써도 순환 참조가 없다.

---

## Task 1: 코드값 Enum 정의 + 백엔드 치환

**Files:**
- Create: `app/constants.py`
- Modify: `app/models/user.py`, `app/auth/router.py`, `app/auth/dependencies.py`, `app/auth/admin_router.py`, `app/auth/seed_admin.py`
- Test: `tests/test_user_model.py`, `tests/test_auth_register.py`, `tests/test_auth_login.py`, `tests/test_auth_refresh_logout.py`, `tests/test_auth_dependencies.py`, `tests/test_auth_me.py`, `tests/test_admin_users.py`, `tests/test_seed_admin.py`, `tests/test_security.py`

**Interfaces:**
- Produces: `app.constants.UserRole` (`MEMBER`, `ADMIN`) 와 `app.constants.UserStatus` (`PENDING`, `ACTIVE`, `DISABLED`, `REJECTED`) — 둘 다 `enum.StrEnum`. Task 2의 마이그레이션과 Task 3의 프론트 타입이 같은 값(대문자 문자열)에 의존한다.
- API 계약 변경(Task 3이 의존): `GET /auth/me` · `POST /auth/login` 응답의 `role`이 `"MEMBER"`/`"ADMIN"`, `POST /auth/register` 응답의 `status`가 `"PENDING"`, `GET /admin/users?status=` 가 `PENDING` 등 대문자를 받는다.

**이 Task는 테스트 DB(테스트마다 새로 만드는 임시 Postgres)만 쓰므로 데이터 마이그레이션 없이 pytest가 통과해야 한다.** 로컬 개발 DB의 기존 데이터 변환은 Task 2가 담당한다.

- [ ] **Step 1: 코드값 Enum 작성**

`app/constants.py` 생성:

```python
from enum import StrEnum


class UserRole(StrEnum):
    """users.role 코드값. DB에 대문자로 저장된다."""

    MEMBER = "MEMBER"
    ADMIN = "ADMIN"


class UserStatus(StrEnum):
    """users.status 코드값. DB에 대문자로 저장된다."""

    PENDING = "PENDING"
    ACTIVE = "ACTIVE"
    DISABLED = "DISABLED"
    REJECTED = "REJECTED"
```

> `StrEnum` 멤버는 `str`의 하위 타입이다. 그래서 aiosql이 돌려주는 순수 문자열과 그대로 비교되고(`row["status"] != UserStatus.ACTIVE`), asyncpg 바인딩·JSON 직렬화도 문자열처럼 동작한다. 별도 변환 코드가 필요 없다.

- [ ] **Step 2: 테스트를 대문자 기대값으로 갱신 (RED를 만든다)**

아래 9개 파일의 소문자 리터럴을 Enum 상수로 바꾼다. 각 파일 맨 위에 `from app.constants import UserRole, UserStatus`(그 파일에서 쓰는 것만) 를 추가한다.

`tests/test_user_model.py` (14-15행):
```python
    assert user.role == UserRole.MEMBER
    assert user.status == UserStatus.PENDING
```

`tests/test_auth_register.py` (7행):
```python
    assert body["status"] == UserStatus.PENDING
```

`tests/test_auth_login.py` (6행, 43행):
```python
async def _create_user(db_session, email: str, password: str, status: str = UserStatus.ACTIVE) -> User:
...
    await _create_user(db_session, "pending@example.com", "pw12345", status=UserStatus.PENDING)
```

`tests/test_auth_refresh_logout.py` (6행):
```python
    user = User(email=email, password_hash=hash_password(password), status=UserStatus.ACTIVE)
```

`tests/test_auth_dependencies.py` (9-10행, 46행, 69행):
```python
async def _login(client, db_session, email: str, role: str = UserRole.MEMBER, password: str = "pw12345"):
    user = User(email=email, password_hash=hash_password(password), role=role, status=UserStatus.ACTIVE)
...
    await _login(client, db_session, "member-only@example.com", role=UserRole.MEMBER)
...
    await _login(client, db_session, "admin-user@example.com", role=UserRole.ADMIN)
```

`tests/test_auth_me.py` (5-6행, 32행, 37행, 41행):
```python
async def _login(client, db_session, email: str, role: str = UserRole.MEMBER, password: str = "pw12345"):
    user = User(email=email, password_hash=hash_password(password), role=role, status=UserStatus.ACTIVE)
...
    assert body["role"] == UserRole.MEMBER
...
    await _login(client, db_session, "me-admin@example.com", role=UserRole.ADMIN)
...
    assert resp.json()["role"] == UserRole.ADMIN
```

`tests/test_admin_users.py` (7행, 24행, 39행, 51행, 64행, 74행):
```python
    admin = User(
        email=email, password_hash=hash_password("pw12345"), role=UserRole.ADMIN, status=UserStatus.ACTIVE
    )
...
    resp = await client.get("/admin/users", params={"status": UserStatus.PENDING})
...
    assert resp.json()["status"] == UserStatus.ACTIVE
...
    assert resp.json()["status"] == UserStatus.REJECTED
...
    member = User(
        email="member-blocked@example.com", password_hash=hash_password("pw12345"),
        role=UserRole.MEMBER, status=UserStatus.ACTIVE,
    )
...
    resp = await client.get("/admin/users", params={"status": UserStatus.PENDING})
```

`tests/test_seed_admin.py` (14-15행):
```python
    assert row["role"] == UserRole.ADMIN
    assert row["status"] == UserStatus.ACTIVE
```

`tests/test_security.py` (27행, 31행, 35행, 50행):
```python
    token = create_access_token(user_id=42, role=UserRole.MEMBER)
...
    assert payload["role"] == UserRole.MEMBER
...
    token = create_access_token(user_id=1, role=UserRole.MEMBER)
...
        "role": UserRole.MEMBER,
```

그리고 `tests/test_admin_users.py` 맨 끝에 **신규 테스트**를 추가한다 — 쿼리 파라미터가 Enum으로 검증되는지 확인한다:

```python
async def test_list_users_rejects_unknown_status(client, db_session):
    await _login_admin(client, db_session, email="admin5@example.com")

    resp = await client.get("/admin/users", params={"status": "nonsense"})
    assert resp.status_code == 422
```

- [ ] **Step 3: 테스트가 실패하는지 확인 (RED)**

Run: `npm test`
Expected: FAIL. 백엔드가 아직 소문자를 쓰므로 대문자를 기대하는 단언들이 깨진다 (예: `assert user.role == UserRole.MEMBER` 에서 `'member' != 'MEMBER'`). 새 422 테스트도 실패한다 — `status`가 아직 `str`이라 `"nonsense"`가 그대로 통과해 200이 돌아온다.

- [ ] **Step 4: 모델 기본값·컬럼 코멘트 치환**

`app/models/user.py` — import 추가:
```python
from app.constants import UserRole, UserStatus
```

`role`/`status` 필드를 교체:
```python
    role: str = Field(
        default=UserRole.MEMBER,
        sa_column_kwargs={"comment": "권한: MEMBER | ADMIN (기본값 MEMBER)"},
    )
    status: str = Field(
        default=UserStatus.PENDING,
        sa_column_kwargs={
            "comment": "가입 상태: PENDING | ACTIVE | DISABLED | REJECTED (기본값 PENDING)"
        },
    )
```

- [ ] **Step 5: 라우터·의존성·시드 치환**

`app/auth/router.py` — import 추가:
```python
from app.constants import UserRole, UserStatus
```

`register` 안의 `insert_user` 호출과 응답(48-65행 부근):
```python
        user_id = await queries.insert_user(
            conn,
            email=email,
            password_hash=hash_password(body.password),
            role=UserRole.MEMBER,
            status=UserStatus.PENDING,
            created_at=now,
            updated_at=now,
        )
...
    return {"id": user_id, "status": UserStatus.PENDING}
```

`login` 안의 상태 검사(105행 부근):
```python
    if row["status"] != UserStatus.ACTIVE:
        raise Errors.forbidden("관리자 승인 대기 중이거나 비활성화된 계정입니다.")
```

`refresh` 안의 상태 검사(147행 부근):
```python
    if user_row is None or user_row["status"] != UserStatus.ACTIVE:
        raise Errors.unauthorized()
```

`app/auth/dependencies.py` — import 추가 후 두 곳(23행, 31행):
```python
from app.constants import UserRole, UserStatus
...
    if row is None or row["status"] != UserStatus.ACTIVE:
        raise Errors.unauthorized("인증 정보가 유효하지 않습니다.")
...
    if user["role"] != UserRole.ADMIN:
        raise Errors.forbidden()
```

`app/auth/admin_router.py` — import 추가 후, 쿼리 파라미터 타입과 승인/거절 값을 교체:
```python
from app.constants import UserStatus
...
@router.get("")
async def list_users(
    # UserStatus로 선언하면 FastAPI가 값을 검증한다 → 잘못된 값은 422로 거절된다.
    status: UserStatus = Query(UserStatus.PENDING),
    db: AsyncSession = Depends(get_db),
    admin: dict = Depends(require_admin),
):
...
@router.post("/{user_id}/approve")
async def approve_user(...):
    return await _set_status(user_id, UserStatus.ACTIVE, db, admin)
...
@router.post("/{user_id}/reject")
async def reject_user(...):
    return await _set_status(user_id, UserStatus.REJECTED, db, admin)
```

`app/auth/seed_admin.py` — import 추가 후 24-25행:
```python
from app.constants import UserRole, UserStatus
...
        role=UserRole.ADMIN,
        status=UserStatus.ACTIVE,
```

- [ ] **Step 6: 테스트 통과 확인 (GREEN)**

Run: `npm test`
Expected: PASS — 기존 72개 + 신규 1개 = **73 passed**

- [ ] **Step 7: 커밋**

```bash
git add app/constants.py app/models/user.py app/auth tests
git commit -m "변경: 공통코드 값(role/status)을 대문자로 통일하고 Enum으로 모음"
```

---

## Task 2: 마이그레이션 + 스키마 문서 일원화

**Files:**
- Create: `alembic/versions/c9f2a17b4d31_uppercase_user_code_values.py`
- Modify: `docs/schema.sql`, `package.json`
- Delete: `docs/SCHEMA.md`

**Interfaces:**
- Consumes: Task 1이 정한 대문자 값(`MEMBER`/`ADMIN`, `PENDING`/`ACTIVE`/`DISABLED`/`REJECTED`).
- Produces: `npm run migrate` 스크립트(= `uv run alembic upgrade head`). 리비전 `c9f2a17b4d31` (down_revision = 현재 head `6b5040798a90`).

- [ ] **Step 1: npm 마이그레이션 스크립트 추가**

이 머신에서는 셸에서 `uv run alembic`을 직접 실행할 수 없다(python.exe 차단, os error 4551). npm을 거치면 동작하므로 루트 `package.json`의 `scripts`에 추가한다:

```json
    "migrate": "uv run alembic upgrade head",
    "migrate:down": "uv run alembic downgrade -1",
```

- [ ] **Step 2: 마이그레이션 파일 작성**

`alembic/versions/c9f2a17b4d31_uppercase_user_code_values.py` 생성:

```python
"""uppercase user code values

Revision ID: c9f2a17b4d31
Revises: 6b5040798a90
Create Date: 2026-07-13

users.role / users.status 의 코드값을 소문자에서 대문자로 통일한다.
기본값은 DB가 아니라 앱 계층(SQLModel Field default)에 있으므로 스키마는 바뀌지 않는다.
바꾸는 것은 (1) 기존 데이터 (2) 컬럼 코멘트의 값 표기 뿐이다.
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = 'c9f2a17b4d31'
down_revision: Union[str, Sequence[str], None] = '6b5040798a90'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # upper()는 이미 대문자인 값에 대해 멱등하므로 재실행해도 안전하다.
    op.execute("UPDATE users SET role = upper(role), status = upper(status)")

    op.alter_column(
        "users",
        "role",
        existing_type=sa.VARCHAR(),
        existing_nullable=False,
        comment="권한: MEMBER | ADMIN (기본값 MEMBER)",
        existing_comment="권한: member | admin (기본값 member)",
    )
    op.alter_column(
        "users",
        "status",
        existing_type=sa.VARCHAR(),
        existing_nullable=False,
        comment="가입 상태: PENDING | ACTIVE | DISABLED | REJECTED (기본값 PENDING)",
        existing_comment="가입 상태: pending | active | disabled | rejected (기본값 pending)",
    )


def downgrade() -> None:
    op.alter_column(
        "users",
        "status",
        existing_type=sa.VARCHAR(),
        existing_nullable=False,
        comment="가입 상태: pending | active | disabled | rejected (기본값 pending)",
        existing_comment="가입 상태: PENDING | ACTIVE | DISABLED | REJECTED (기본값 PENDING)",
    )
    op.alter_column(
        "users",
        "role",
        existing_type=sa.VARCHAR(),
        existing_nullable=False,
        comment="권한: member | admin (기본값 member)",
        existing_comment="권한: MEMBER | ADMIN (기본값 MEMBER)",
    )

    op.execute("UPDATE users SET role = lower(role), status = lower(status)")
```

- [ ] **Step 3: 마이그레이션 체인 회귀 테스트**

Run: `npm test`
Expected: PASS (73개). 특히 `tests/test_alembic_migration.py::test_alembic_upgrade_head_applies_cleanly_on_fresh_db` 가 새 리비전을 포함한 체인 전체를 빈 DB에 적용해 통과해야 한다.

- [ ] **Step 4: 로컬 개발 DB에 실제 적용 후 데이터 확인**

DB가 떠 있어야 한다(`docker compose up -d db`).

Run: `npm run migrate`
Expected: `Running upgrade 6b5040798a90 -> c9f2a17b4d31, uppercase user code values`

그 다음 실제 데이터를 확인한다:

Run: `docker compose exec -T db psql -U studio -d studio -c "SELECT email, role, status FROM users;"`
Expected: 기존 계정의 `role`이 `ADMIN`, `status`가 `ACTIVE` 로 바뀌어 있다 (소문자 값이 하나도 남아 있지 않다).

컬럼 코멘트도 확인한다:

Run: `docker compose exec -T db psql -U studio -d studio -c "SELECT col_description('users'::regclass, ordinal_position) AS comment, column_name FROM information_schema.columns WHERE table_name='users' AND column_name IN ('role','status');"`
Expected: 코멘트가 대문자 표기(`권한: MEMBER | ADMIN (기본값 MEMBER)` 등)로 바뀌어 있다.

- [ ] **Step 5: `docs/schema.sql` 갱신 — 코멘트 대문자화 + `SCHEMA.md` 고유 내용 흡수**

`docs/schema.sql`의 상단 주석 블록(1-11행)을 아래로 교체한다. `SCHEMA.md`가 지워지므로, 거기에만 있던 **테이블 생성 규칙**과 **지운 테이블 이력**을 여기로 옮긴다:

```sql
-- Studio DB 스키마 DDL (문서용 참고 스냅샷)
--
-- 실제 스키마는 Alembic 마이그레이션(alembic/versions/*.py)이 기준(source of truth)이며,
-- 이 파일은 사람이 읽기 편하도록 같은 스키마를 순수 DDL로 정리한 것이다.
-- 이 파일을 직접 실행해서 DB를 만들지 않는다 (`npm run migrate`를 사용할 것).
-- 테이블을 추가/변경할 때마다 이 파일을 갱신한다.
--
-- ─── 테이블 생성 규칙: 컬럼 순서는 id → 업무 컬럼 → 감사 컬럼 ───
--
-- 모든 테이블은 id, 업무 컬럼들, created_at/created_by/updated_at/updated_by 순서로 정렬된다.
-- app/models/base.py의 BaseEntity는 id만 제공하는 믹스인이다. 감사 컬럼 4개를 믹스인에
-- 넣지 않는 이유: Python/SQLAlchemy 상속 규칙상 믹스인이 선언한 컬럼은 항상 서브클래스의
-- 업무 컬럼보다 앞에 오기 때문에, "업무 컬럼 뒤에 감사 컬럼" 순서를 만들 수 없다.
-- 그래서 감사 컬럼은 base.py의 *_field() 헬퍼로 설정만 한 곳에서 관리하고, 각 테이블
-- 클래스가 본문 맨 아래에서 명시적으로 호출해 선언한다.
--
-- ─── created_at/updated_at 기본값이 plain now()가 아닌 이유 ───
--
-- DB 세션/서버 타임존이 UTC일 수 있어(예: 로컬 개발용 Postgres 컨테이너), now()를 그대로
-- naive TIMESTAMP 컬럼에 넣으면 UTC 벽시계 시각이 저장되어 로컬시간 저장 규칙이 깨진다.
-- 항상 Asia/Seoul 벽시계 시각으로 변환해서 저장하도록 timezone() 함수를 명시적으로 쓴다.
-- 단, 이 표현식은 DB SQL이라 APP_TIMEZONE 설정(런타임)을 반영하지 않고 Asia/Seoul로 고정된다.
--
-- ─── 공통코드 값은 대문자 ───
--
-- role/status 같은 코드값은 DB·API·프론트에서 모두 대문자로 통일한다.
-- 값의 정의는 app/constants.py의 StrEnum(UserRole, UserStatus)이 유일한 출처다.
--
-- ─── 지운 테이블 ───
--
-- error_codes: 에러 코드를 DB 카탈로그로 관리하던 초기 설계의 잔재. 소스 관리 방식
-- (app/utils/errors.py의 AppError/Errors)으로 전환하며 삭제했다.
-- 마이그레이션 체인에는 생성(94c0f2fa9ffe)과 삭제(f1515bf03a82)가 모두 남아 있다.
```

그리고 `role`/`status`의 컬럼 코멘트(33-34행)를 대문자 표기로 바꾼다:

```sql
COMMENT ON COLUMN users.role IS '권한: MEMBER | ADMIN (기본값 MEMBER)';
COMMENT ON COLUMN users.status IS '가입 상태: PENDING | ACTIVE | DISABLED | REJECTED (기본값 PENDING)';
```

- [ ] **Step 6: `docs/SCHEMA.md` 삭제**

```bash
git rm docs/SCHEMA.md
```

`docs/SCHEMA.md`를 참조하는 다른 파일이 남아 있지 않은지 확인한다:

Run: `grep -rn "SCHEMA.md" --exclude-dir=.git .`
Expected: `docs/superpowers/` 아래의 설계·계획 문서(이 계획 자체 포함)를 제외하면 참조가 없다. `docs/schema.sql`에는 Step 5에서 이미 참조 문구를 지웠다.

- [ ] **Step 7: 커밋**

```bash
git add alembic/versions/c9f2a17b4d31_uppercase_user_code_values.py docs/schema.sql package.json
git rm docs/SCHEMA.md
git commit -m "변경: 기존 코드값 데이터를 대문자로 마이그레이션하고 스키마 문서를 schema.sql로 일원화"
```

---

## Task 3: 프론트 타입 대문자

**Files:**
- Modify: `web/src/lib/auth.tsx`

**Interfaces:**
- Consumes: Task 1이 바꾼 API 응답 — `GET /auth/me` · `POST /auth/login` 의 `role`이 `"MEMBER"` | `"ADMIN"`.
- Produces: `web/src/lib/auth.tsx`의 `export type User = { id: number; email: string; role: 'MEMBER' | 'ADMIN' }`.

- [ ] **Step 1: `User` 타입 갱신**

`web/src/lib/auth.tsx`의 `User` 타입(7행 부근):

```tsx
export type User = {
  id: number
  email: string
  role: 'MEMBER' | 'ADMIN'
}
```

이 파일에서 다른 변경은 없다. 프론트에는 role 값을 비교하는 로직이 아직 없고(라우트 가드는 로그인 여부만 본다), `web/src/pages/Dashboard.tsx`가 `user.role`을 그대로 출력한다 — 화면에 `ADMIN`으로 표시되는 것이 의도된 동작이다. 한글 라벨링은 이번 범위가 아니므로 `Dashboard.tsx`를 건드리지 않는다.

- [ ] **Step 2: 빌드 확인**

Run: `npm run build`
Expected: TypeScript 컴파일 통과, 에러 없음.

- [ ] **Step 3: 브라우저 확인**

`npm run dev`로 띄운 뒤(백엔드·프론트 동시 기동):

1. 기존 로그인 세션이 있다면 **로그아웃 후 다시 로그인한다.** (기존 액세스 토큰에는 소문자 `role`이 박혀 있어, 만료 전까지 `require_admin`이 그 토큰을 관리자로 인정하지 않는다.)
2. 관리자 계정으로 로그인 → 대시보드에 이메일과 함께 **`ADMIN`** 이 표시된다.
3. DevTools Network에서 `GET /auth/me` 응답이 `{"id":…,"email":…,"role":"ADMIN"}` 인지 확인한다.

- [ ] **Step 4: 커밋**

```bash
git add web/src/lib/auth.tsx
git commit -m "변경: 프론트 User.role 타입을 대문자 코드값으로 갱신"
```

---

## 완료 조건

- `npm test` 통과 (73개)
- `npm run build` 통과
- `npm run migrate` 후 로컬 DB의 `users.role`/`users.status`에 소문자 값이 하나도 없다
- 재로그인 후 대시보드에 `ADMIN`이 표시된다
- `docs/SCHEMA.md`가 삭제되고, 그 고유 내용(테이블 생성 규칙·지운 테이블 이력)이 `docs/schema.sql` 상단 주석에 남아 있다

## 다음 작업 (이번 범위 밖)

- 화면의 한글 라벨링 (`ADMIN` → "관리자", `PENDING` → "승인 대기")
- `Project`/`Stage`/`Asset` 모델을 만들 때 `ProjectStatus`·`StageName`·`StageStatus`·`AssetKind`를 같은 규칙(대문자 + `app/constants.py`의 StrEnum)으로 추가
