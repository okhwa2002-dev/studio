# 계정 잠금 관리 구현 계획

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 연속 로그인 실패 5회에 계정을 잠그고(관리자 수동 해제), 관리자 화면에서 실패 횟수·잠김·해제일시를 보고 잠금을 해제할 수 있게 한다.

**Architecture:** `User`에 컬럼 3개(`failed_login_count`, `locked_at`, `unlocked_at`)를 더한다. 로그인 로직이 실패를 세어 임계치에서 `locked_at`을 채우고, 오답은 항상 통일 401을 반환한다(잠김 노출 방지). 관리자 `unlock` 엔드포인트가 셋을 초기화한다. 프론트는 목록에 세 필드와 "잠금 해제" 버튼을 더한다.

**Tech Stack:** FastAPI + SQLModel + alembic + aiosql(raw SQL) + asyncpg / pytest(testcontainers). 프론트 React 19 + TS + Tailwind v4.

**설계 문서:** `docs/superpowers/specs/2026-07-15-account-lockout-design.md`

## Global Constraints

- **잠금은 `status`와 직교한다.** ACTIVE이면서 잠긴 상태가 가능. status에 잠금 값을 넣지 말 것. 잠김여부는 `locked_at IS NOT NULL`로 파생한다(별도 불리언 컬럼 금지).
- **임계치는 설정값** `failed_login_limit`(기본 5). 로그인 로직은 `get_settings().failed_login_limit`을 읽는다. 매직넘버 5를 코드에 박지 말 것.
- **보안 불변식:** 비밀번호가 틀리면 잠김 여부와 무관하게 **항상 통일된 401**(`"이메일 또는 비밀번호가 올바르지 않습니다."`)을 반환한다. 잠김 메시지(423)는 비밀번호가 맞는 사용자에게만. 기존 타이밍 방어(더미 해시)를 유지하고 `row is None or not verify_password(...)`로 단축 평가 합치지 말 것.
- **날짜는 로컬 벽시계** `now_local()`로 저장(기존 규칙). JWT의 iat/exp(UTC)와는 별개.
- **role/status 값은 대문자.** 프론트도 대문자로 비교.
- **테스트:** 백엔드는 pytest(TDD). 테스트는 `SQLModel.metadata.create_all`로 스키마를 만들므로(마이그레이션 미실행) 모델 필드가 정확해야 한다. 프론트는 테스트 러너가 없어 `npm run lint`+`npm run build`+수동 확인으로 검증.
- **명령 위치:** 백엔드 `uv run pytest`(루트), 프론트 `npm run lint`/`npm run build`(루트).
- **커밋은 사용자가 직접.** 각 태스크 커밋 단계는 제안 메시지. 커밋 시 `git add -A` 금지 — 해당 태스크가 만진 파일만 스테이징(워킹 트리에 이 기능과 무관한 미커밋 프론트 변경이 있다).

---

## File Structure

| 파일 | 변경 |
|------|------|
| `app/models/user.py` | 컬럼 3개 추가 |
| `app/config.py` | `failed_login_limit: int = 5` |
| `alembic/versions/<new>.py` | 컬럼 3개 add/drop |
| `app/queries/users.sql` | 기존 3개 SELECT 확장 + 신규 쿼리 3개 |
| `app/utils/errors.py` | `Errors.locked` (423) |
| `app/auth/router.py` | `login`에 잠금 로직 |
| `app/auth/admin_router.py` | `unlock_user` 엔드포인트 |
| `web/src/lib/admin.ts` | `AdminUser` 필드 + `adminUsers.unlock` |
| `web/src/pages/admin/AdminUsers.tsx` | 열 3개 + 잠금 해제 액션 |
| `tests/test_account_lockout.py` (신규) | 잠금/해제 통합 테스트 |

---

## Task 1: 스키마 — 모델·설정·마이그레이션·SELECT 확장

컬럼 3개를 모델·DB·조회 쿼리에 반영한다. 화면·로직이 얹힐 토대다.

**Files:**
- Modify: `app/models/user.py`
- Modify: `app/config.py`
- Create: `alembic/versions/<new>.py`
- Modify: `app/queries/users.sql` (SELECT 3개 확장)
- Create: `tests/test_account_lockout.py`

**Interfaces:**
- Produces:
  - `User.failed_login_count: int` (default 0), `User.locked_at: Optional[datetime]`, `User.unlocked_at: Optional[datetime]`
  - `Settings.failed_login_limit: int` (default 5)
  - `find_by_email`/`find_by_id`/`list_by_status`가 위 세 컬럼을 반환

- [ ] **Step 1: 모델 기본값 테스트 작성 (`tests/test_account_lockout.py` 신규)**

```python
from app.auth.security import hash_password
from app.constants import UserStatus
from app.db import raw_connection
from app.models.user import User
from app.queries import queries


async def test_new_user_lock_fields_default(db_session):
    user = User(email="lockdefault@example.com", password_hash=hash_password("pw12345"))
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    assert user.failed_login_count == 0
    assert user.locked_at is None
    assert user.unlocked_at is None


async def test_find_by_email_returns_lock_fields(db_session):
    # 로그인 로직이 읽을 수 있도록 SELECT가 잠금 컬럼을 포함해야 한다.
    user = User(email="lockcols@example.com", password_hash=hash_password("pw12345"), status=UserStatus.ACTIVE)
    db_session.add(user)
    await db_session.commit()
    conn = await raw_connection(db_session)
    row = await queries.find_by_email(conn, email="lockcols@example.com")
    assert "failed_login_count" in row
    assert "locked_at" in row
    assert "unlocked_at" in row
```

- [ ] **Step 2: 테스트 실행 → 실패 확인**

Run: `uv run pytest tests/test_account_lockout.py -v`
Expected: FAIL — `User`에 `failed_login_count` 속성이 없어 `AttributeError`(또는 컬럼 없음).

- [ ] **Step 3: 모델에 컬럼 3개 추가 (`app/models/user.py`)**

`approved_by` 필드 블록 다음, `created_at = created_at_field()` 앞에 추가한다(컬럼 순서: id → 업무 → 감사 유지). `failed_login_count`는 `server_default="0"`을 준다 — 회원가입의 raw INSERT(`insert_user`)가 이 컬럼을 넣지 않으므로 DB 기본값이 필요하다.

```python
    failed_login_count: int = Field(
        default=0,
        sa_column_kwargs={
            "server_default": "0",
            "comment": "연속 로그인 실패 횟수 (성공 시 0으로 리셋)",
        },
    )
    locked_at: Optional[datetime] = Field(
        default=None,
        sa_column_kwargs={"comment": "계정 잠긴 시각 (NULL=안 잠김, 값 있음=잠김)"},
    )
    unlocked_at: Optional[datetime] = Field(
        default=None,
        sa_column_kwargs={"comment": "관리자가 잠금 해제한 시각 (해제일시)"},
    )
```

- [ ] **Step 4: 설정에 임계치 추가 (`app/config.py`)**

`log_sql: bool = False` 아래에 추가한다.

```python
    failed_login_limit: int = 5
```

- [ ] **Step 5: SELECT 쿼리 3개 확장 (`app/queries/users.sql`)**

`find_by_email`, `find_by_id`, `list_by_status`의 SELECT 목록에 `failed_login_count, locked_at, unlocked_at`을 추가한다. 아래가 변경 후 전체 모습이다.

```sql
-- name: find_by_email^
SELECT id, email, password_hash, role, status, approved_at, approved_by,
       failed_login_count, locked_at, unlocked_at,
       created_at, updated_at, created_by, updated_by
FROM users
WHERE email = :email;

-- name: find_by_id^
SELECT id, email, password_hash, role, status, approved_at, approved_by,
       failed_login_count, locked_at, unlocked_at,
       created_at, updated_at, created_by, updated_by
FROM users
WHERE id = :id;

-- name: list_by_status
SELECT id, email, role, status, approved_at, approved_by,
       failed_login_count, locked_at, unlocked_at,
       created_at, updated_at
FROM users
WHERE status = :status
ORDER BY created_at ASC;
```

- [ ] **Step 6: 테스트 실행 → 통과 확인**

Run: `uv run pytest tests/test_account_lockout.py -v`
Expected: PASS (2 tests).

- [ ] **Step 7: 마이그레이션 생성**

alembic이 down_revision을 자동으로 현재 head로 채우도록 빈 리비전을 만든 뒤 본문을 채운다.

Run: `uv run alembic revision -m "add account lockout columns"`

생성된 파일의 `upgrade`/`downgrade`를 아래로 채운다(다른 컬럼·주석·down_revision 등은 건드리지 않는다).

```python
def upgrade() -> None:
    op.add_column('users', sa.Column('failed_login_count', sa.Integer(), nullable=False, server_default='0', comment='연속 로그인 실패 횟수 (성공 시 0으로 리셋)'))
    op.add_column('users', sa.Column('locked_at', sa.DateTime(), nullable=True, comment='계정 잠긴 시각 (NULL=안 잠김, 값 있음=잠김)'))
    op.add_column('users', sa.Column('unlocked_at', sa.DateTime(), nullable=True, comment='관리자가 잠금 해제한 시각 (해제일시)'))


def downgrade() -> None:
    op.drop_column('users', 'unlocked_at')
    op.drop_column('users', 'locked_at')
    op.drop_column('users', 'failed_login_count')
```

- [ ] **Step 8: 전체 테스트 실행 (회귀 + 마이그레이션 검증)**

Run: `uv run pytest`
Expected: 전부 통과. 기존 로그인/회원가입/관리자 테스트가 새 컬럼(기본값 존재)으로도 깨지지 않아야 한다. 마이그레이션 검증 테스트(`tests/test_alembic_migration.py`)가 있으면 새 리비전 up/down이 함께 검증된다.

- [ ] **Step 9: 커밋 (사용자에게 제안)**

`git add app/models/user.py app/config.py app/queries/users.sql alembic/versions/<new>.py tests/test_account_lockout.py`

```
기능: 계정 잠금 컬럼(실패 횟수·잠김·해제일시) 스키마 추가
```

---

## Task 2: 로그인 잠금 로직

로그인이 실패를 세어 임계치에서 잠그고, 잠긴 계정을 거부한다. 잠금/실패 카운트 쓰기 쿼리와 423 에러 헬퍼를 여기서 만든다.

**Files:**
- Modify: `app/utils/errors.py`
- Modify: `app/queries/users.sql` (신규 쿼리 2개)
- Modify: `app/auth/router.py` (`login`)
- Modify: `tests/test_account_lockout.py`

**Interfaces:**
- Consumes: Task 1의 `find_by_email`(잠금 컬럼 포함), `Settings.failed_login_limit`, `now_local`
- Produces: `Errors.locked()` → 423; `record_failed_login!`, `reset_failed_login!` 쿼리

- [ ] **Step 1: 로그인 잠금 테스트 작성 (`tests/test_account_lockout.py`에 추가)**

파일 상단 import에 `import app.auth.router as auth_router`를 추가하고, 아래 테스트를 덧붙인다.

```python
async def _active(db_session, email, password="pw12345"):
    user = User(email=email, password_hash=hash_password(password), status=UserStatus.ACTIVE)
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    return user


async def test_five_failures_locks_account(client, db_session):
    user = await _active(db_session, "lock5@example.com")
    for _ in range(5):
        resp = await client.post("/auth/login", json={"email": "lock5@example.com", "password": "wrong"})
        assert resp.status_code == 401  # 매 응답은 통일 401
    await db_session.refresh(user)
    assert user.failed_login_count == 5
    assert user.locked_at is not None


async def test_locked_account_correct_password_returns_423(client, db_session):
    user = await _active(db_session, "locked423@example.com")
    for _ in range(5):
        await client.post("/auth/login", json={"email": "locked423@example.com", "password": "wrong"})
    resp = await client.post("/auth/login", json={"email": "locked423@example.com", "password": "pw12345"})
    assert resp.status_code == 423
    assert "access_token" not in resp.cookies


async def test_locked_account_wrong_password_still_401(client, db_session):
    # 잠긴 계정이라도 오답에는 통일 401 — 공격자에게 잠김이 드러나지 않는다.
    await _active(db_session, "lockedwrong@example.com")
    for _ in range(5):
        await client.post("/auth/login", json={"email": "lockedwrong@example.com", "password": "wrong"})
    resp = await client.post("/auth/login", json={"email": "lockedwrong@example.com", "password": "wrong"})
    assert resp.status_code == 401


async def test_successful_login_resets_failure_count(client, db_session):
    user = await _active(db_session, "reset@example.com")
    for _ in range(3):
        await client.post("/auth/login", json={"email": "reset@example.com", "password": "wrong"})
    resp = await client.post("/auth/login", json={"email": "reset@example.com", "password": "pw12345"})
    assert resp.status_code == 200
    await db_session.refresh(user)
    assert user.failed_login_count == 0


async def test_lock_threshold_is_configurable(client, db_session, monkeypatch):
    user = await _active(db_session, "cfg@example.com")
    # 캐시된 settings 인스턴스의 속성만 바꾼다(monkeypatch가 자동 복원).
    monkeypatch.setattr(auth_router.get_settings(), "failed_login_limit", 3)
    for _ in range(3):
        await client.post("/auth/login", json={"email": "cfg@example.com", "password": "wrong"})
    await db_session.refresh(user)
    assert user.locked_at is not None
```

- [ ] **Step 2: 테스트 실행 → 실패 확인**

Run: `uv run pytest tests/test_account_lockout.py -v`
Expected: FAIL — 잠금 로직이 없어 5회 실패 후에도 `locked_at`이 None, 잠긴 계정도 200/403을 반환.

- [ ] **Step 3: 423 에러 헬퍼 추가 (`app/utils/errors.py`)**

`Errors` 클래스의 `unauthorized` 아래에 추가한다.

```python
    @staticmethod
    def locked(message: str = "계정이 잠겼습니다. 관리자에게 문의하세요.") -> AppError:
        return AppError(423, "ACCOUNT_LOCKED", message)
```

- [ ] **Step 4: 쓰기 쿼리 2개 추가 (`app/queries/users.sql` 끝에)**

```sql
-- name: record_failed_login!
UPDATE users
SET failed_login_count = :failed_login_count,
    locked_at = :locked_at,
    updated_at = :updated_at
WHERE id = :id;

-- name: reset_failed_login!
UPDATE users
SET failed_login_count = 0,
    updated_at = :updated_at
WHERE id = :id;
```

- [ ] **Step 5: 로그인 로직 교체 (`app/auth/router.py`의 `login`)**

`login` 함수 본문을 아래로 교체한다(시그니처·데코레이터는 그대로). `Errors.locked`와 `get_settings`는 이미 import되어 있다.

```python
@router.post("/login")
async def login(body: LoginRequest, response: Response, db: AsyncSession = Depends(get_db)):
    conn = await raw_connection(db)
    email = body.email.strip().lower()
    row = await queries.find_by_email(conn, email=email)
    if row is None:
        # 더미 해시로라도 verify_password를 호출해 존재하는 계정과 동일한 연산
        # 비용을 지불한다(타이밍 사이드채널 방지). 셀 계정이 없으므로 카운트 없음.
        verify_password(body.password, _DUMMY_PASSWORD_HASH)
        raise Errors.unauthorized("이메일 또는 비밀번호가 올바르지 않습니다.")

    now = now_local()
    if not verify_password(body.password, row["password_hash"]):
        # 실패 카운트 증가. 임계치 도달 시 잠근다. 이미 잠겼으면 잠금 시각을 유지한다.
        new_count = row["failed_login_count"] + 1
        if row["locked_at"] is not None:
            new_locked_at = row["locked_at"]
        elif new_count >= get_settings().failed_login_limit:
            new_locked_at = now
        else:
            new_locked_at = None
        await queries.record_failed_login(
            conn, id=row["id"], failed_login_count=new_count, locked_at=new_locked_at, updated_at=now
        )
        await db.commit()
        # 오답은 잠김 여부와 무관하게 항상 통일 401. 공격자에게 잠김을 드러내지 않는다.
        raise Errors.unauthorized("이메일 또는 비밀번호가 올바르지 않습니다.")

    # 비밀번호는 맞음. 잠김은 status와 별개로 먼저 막는다(진짜 사용자에게만 423).
    if row["locked_at"] is not None:
        raise Errors.locked()
    if row["status"] != UserStatus.ACTIVE:
        raise Errors.forbidden("관리자 승인 대기 중이거나 비활성화된 계정입니다.")

    if row["failed_login_count"] > 0:
        await queries.reset_failed_login(conn, id=row["id"], updated_at=now)

    access_token = create_access_token(row["id"], row["role"])
    refresh_token = generate_refresh_token()
    await queries.insert_refresh_token(
        conn,
        user_id=row["id"],
        token_hash=hash_refresh_token(refresh_token),
        expires_at=now + timedelta(days=REFRESH_TOKEN_DAYS),
        created_at=now,
        updated_at=now,
    )
    await db.commit()

    _set_auth_cookies(response, access_token, refresh_token)
    return {"id": row["id"], "email": row["email"], "role": row["role"]}
```

- [ ] **Step 6: 테스트 실행 → 통과 확인**

Run: `uv run pytest tests/test_account_lockout.py -v`
Expected: PASS (Task 1의 2개 + Task 2의 5개 = 7개).

- [ ] **Step 7: 전체 테스트 (회귀)**

Run: `uv run pytest`
Expected: 전부 통과. 기존 로그인 테스트(오답 401, 미지 이메일 401, pending 403, 타이밍 스파이)가 그대로 통과해야 한다.

- [ ] **Step 8: 커밋 (사용자에게 제안)**

`git add app/utils/errors.py app/queries/users.sql app/auth/router.py tests/test_account_lockout.py`

```
기능: 로그인 실패 5회 시 계정 잠금 (오답은 통일 401 유지)
```

---

## Task 3: 관리자 잠금 해제 API

관리자가 잠긴 계정을 해제하는 엔드포인트. 기존 approve/reject와 같은 형태.

**Files:**
- Modify: `app/queries/users.sql` (신규 쿼리 1개)
- Modify: `app/auth/admin_router.py`
- Modify: `tests/test_account_lockout.py`

**Interfaces:**
- Consumes: Task 1의 `find_by_id`, `require_admin`, `now_local`, `Errors.not_found`
- Produces: `POST /admin/users/{user_id}/unlock` → `{id, unlocked_at}`; `unlock_user!` 쿼리

- [ ] **Step 1: 해제 테스트 작성 (`tests/test_account_lockout.py`에 추가)**

파일 상단 import에 `from app.constants import UserRole`를 추가(없으면)하고, 아래를 덧붙인다.

```python
async def _login_admin(client, db_session, email="lockadmin@example.com"):
    admin = User(email=email, password_hash=hash_password("pw12345"), role=UserRole.ADMIN, status=UserStatus.ACTIVE)
    db_session.add(admin)
    await db_session.commit()
    await db_session.refresh(admin)
    resp = await client.post("/auth/login", json={"email": email, "password": "pw12345"})
    assert resp.status_code == 200
    return admin


async def test_unlock_clears_lock_and_resets_count(client, db_session):
    await _login_admin(client, db_session, email="unlockadmin@example.com")
    target = await _active(db_session, "tounlock@example.com")
    for _ in range(5):
        await client.post("/auth/login", json={"email": "tounlock@example.com", "password": "wrong"})
    await db_session.refresh(target)
    assert target.locked_at is not None

    resp = await client.post(f"/admin/users/{target.id}/unlock")
    assert resp.status_code == 200
    await db_session.refresh(target)
    assert target.locked_at is None
    assert target.failed_login_count == 0
    assert target.unlocked_at is not None

    # 해제 후 다시 로그인 가능
    resp = await client.post("/auth/login", json={"email": "tounlock@example.com", "password": "pw12345"})
    assert resp.status_code == 200


async def test_unlock_unknown_user_returns_404(client, db_session):
    await _login_admin(client, db_session, email="unlock404@example.com")
    resp = await client.post("/admin/users/999999/unlock")
    assert resp.status_code == 404


async def test_unlock_rejects_non_admin(client, db_session):
    member = User(email="unlockmember@example.com", password_hash=hash_password("pw12345"), role=UserRole.MEMBER, status=UserStatus.ACTIVE)
    db_session.add(member)
    await db_session.commit()
    await client.post("/auth/login", json={"email": "unlockmember@example.com", "password": "pw12345"})
    resp = await client.post("/admin/users/1/unlock")
    assert resp.status_code == 403
```

- [ ] **Step 2: 테스트 실행 → 실패 확인**

Run: `uv run pytest tests/test_account_lockout.py -k unlock -v`
Expected: FAIL — `/unlock` 라우트가 없어 404(라우트 미존재) 또는 405.

- [ ] **Step 3: 해제 쿼리 추가 (`app/queries/users.sql` 끝에)**

```sql
-- name: unlock_user!
UPDATE users
SET locked_at = NULL,
    failed_login_count = 0,
    unlocked_at = :unlocked_at,
    updated_at = :updated_at,
    updated_by = :updated_by
WHERE id = :id;
```

- [ ] **Step 4: 해제 엔드포인트 추가 (`app/auth/admin_router.py` 끝에)**

기존 `reject_user` 아래에 추가한다. `find_by_id`·`now_local`·`Errors`는 이미 import되어 있다.

```python
@router.post("/{user_id}/unlock")
async def unlock_user(
    user_id: int,
    db: AsyncSession = Depends(get_db),
    admin: dict = Depends(require_admin),
):
    conn = await raw_connection(db)
    row = await queries.find_by_id(conn, id=user_id)
    if row is None:
        raise Errors.not_found("사용자를 찾을 수 없습니다.")

    now = now_local()
    await queries.unlock_user(
        conn, id=user_id, unlocked_at=now, updated_at=now, updated_by=admin["id"]
    )
    await db.commit()
    return {"id": user_id, "unlocked_at": now}
```

- [ ] **Step 5: 테스트 실행 → 통과 확인**

Run: `uv run pytest tests/test_account_lockout.py -v`
Expected: PASS (Task 1·2·3 합쳐 10개).

- [ ] **Step 6: 전체 테스트 (회귀)**

Run: `uv run pytest`
Expected: 전부 통과.

- [ ] **Step 7: 커밋 (사용자에게 제안)**

`git add app/queries/users.sql app/auth/admin_router.py tests/test_account_lockout.py`

```
기능: 관리자 계정 잠금 해제 API (POST /admin/users/{id}/unlock)
```

---

## Task 4: 관리자 화면 — 잠금 표시·해제 버튼

목록에 실패 횟수·잠김·해제일시를 보여주고, 잠긴 행에 "잠금 해제" 버튼을 단다.

**Files:**
- Modify: `web/src/lib/admin.ts`
- Modify: `web/src/pages/admin/AdminUsers.tsx`

**Interfaces:**
- Consumes: Task 3의 `POST /admin/users/{id}/unlock`, Task 1의 확장된 `list_by_status`(잠금 필드 포함)
- Produces: 없음 (기능 완성)

- [ ] **Step 1: `lib/admin.ts` — 타입 필드와 `unlock` 추가**

`AdminUser` 타입에 필드 3개를 더하고, `adminUsers`에 `unlock`을 추가한다.

```ts
export type AdminUser = {
  id: number
  email: string
  role: 'MEMBER' | 'ADMIN'
  status: 'PENDING' | 'ACTIVE' | 'DISABLED' | 'REJECTED'
  created_at: string
  approved_at: string | null
  failed_login_count: number
  locked_at: string | null
  unlocked_at: string | null
}

export const adminUsers = {
  list: (status: AdminUser['status']) => api.get<AdminUser[]>(`/admin/users?status=${status}`),
  approve: (id: number) => api.post<{ id: number; status: string }>(`/admin/users/${id}/approve`),
  reject: (id: number) => api.post<{ id: number; status: string }>(`/admin/users/${id}/reject`),
  unlock: (id: number) => api.post<{ id: number; unlocked_at: string }>(`/admin/users/${id}/unlock`),
}
```

- [ ] **Step 2: `AdminUsers.tsx` — `act`에 unlock 허용**

`act`의 action 타입에 `'unlock'`을 더한다. `adminUsers[action]`이 그대로 동작한다.

```tsx
  const act = async (id: number, action: 'approve' | 'reject' | 'unlock') => {
    setActingId(id)
    setError(null)
    try {
      await adminUsers[action](id)
      load() // 처리된 사용자는 현재 목록에서 빠지거나 상태가 바뀐다
    } catch (e) {
      setError(e instanceof ApiError ? e.message : UNKNOWN)
    } finally {
      setActingId(null)
    }
  }
```

- [ ] **Step 3: `AdminUsers.tsx` — 잠김 배지 컴포넌트 추가**

`StatusBadge` 함수 아래(컴포넌트 바깥)에 추가한다.

```tsx
function LockBadge() {
  return (
    <span className="rounded-full bg-red-100 px-2 py-0.5 text-xs font-medium text-red-800">
      🔒 잠김
    </span>
  )
}
```

- [ ] **Step 4: `AdminUsers.tsx` — 컬럼과 액션 교체**

`columns`와 `columnsWithAction` 정의를 아래로 통째 교체한다. 실패·잠김·해제일시 열을 더하고, 액션 열("관리")을 항상 두되 셀 내용을 행 상태에 따라 바꾼다(PENDING → 승인/거절, 잠김 → 잠금 해제, 그 외 → 없음).

```tsx
  const columns: Column<AdminUser>[] = [
    { header: '이메일', cell: (u) => u.email },
    { header: '역할', cell: (u) => roleLabel(u.role) },
    { header: '상태', cell: (u) => <StatusBadge status={u.status} /> },
    { header: '실패', cell: (u) => (u.failed_login_count > 0 ? u.failed_login_count : '-'), align: 'right' },
    { header: '잠김', cell: (u) => (u.locked_at ? <LockBadge /> : '-') },
    { header: '가입일', cell: (u) => formatDate(u.created_at), align: 'right' },
    { header: '해제일시', cell: (u) => (u.unlocked_at ? formatDate(u.unlocked_at) : '-'), align: 'right' },
    {
      header: '관리',
      align: 'right',
      cell: (u) => {
        if (u.status === 'PENDING') {
          return (
            <div className="flex justify-end gap-2">
              <button
                onClick={() => act(u.id, 'approve')}
                disabled={actingId !== null}
                className="rounded-md bg-slate-900 px-3 py-1 text-xs font-medium text-white disabled:opacity-50"
              >
                승인
              </button>
              <button
                onClick={() => act(u.id, 'reject')}
                disabled={actingId !== null}
                className="rounded-md border border-slate-300 px-3 py-1 text-xs font-medium text-slate-700 hover:bg-slate-50 disabled:opacity-50"
              >
                거절
              </button>
            </div>
          )
        }
        if (u.locked_at) {
          return (
            <div className="flex justify-end">
              <button
                onClick={() => act(u.id, 'unlock')}
                disabled={actingId !== null}
                className="rounded-md border border-slate-300 px-3 py-1 text-xs font-medium text-slate-700 hover:bg-slate-50 disabled:opacity-50"
              >
                잠금 해제
              </button>
            </div>
          )
        }
        return null
      },
    },
  ]

  const columnsWithAction = columns
```

> `columnsWithAction`은 이제 조건 분기가 없다(액션 열이 항상 포함됨). 아래 `<Table columns={columnsWithAction} ... />`는 그대로 두면 된다. 변수를 없애고 `columns`를 직접 넘겨도 되지만, 기존 참조를 깨지 않도록 별칭만 남긴다.

- [ ] **Step 5: 린트·빌드**

Run: `npm run lint` 그리고 `npm run build`
Expected: 둘 다 통과. (`auth.tsx:62`의 기존 react-refresh 경고 외 새 경고 없음.)

- [ ] **Step 6: 전체 수동 검증 (설계 문서 7장)**

Run: `npm run dev` → http://localhost:5173. admin 계정으로.

| # | 확인 | 기대 |
|---|------|------|
| 1 | 목록 표시 | 실패 횟수·잠김·해제일시 열이 보인다 |
| 2 | 어떤 계정을 로그아웃 상태에서 5회 오답 로그인 | 그 계정이 잠긴다(6번째 정답 시 잠김 메시지) |
| 3 | 잠긴 계정이 있는 탭(보통 활성) | 잠김 배지 🔒와 "잠금 해제" 버튼이 보인다 |
| 4 | "잠금 해제" 클릭 | 배지가 사라지고 실패 0, 해제일시가 채워진다 |
| 5 | 해제 후 그 계정으로 로그인 | 성공한다 |
| 6 | 잠긴 상태에서 올바른 비밀번호로 로그인 | 로그인 화면에 "계정이 잠겼습니다…" 메시지(423, 기존 else 분기가 표시) |
| 7 | 처리 중 | 버튼이 비활성화된다 |

- [ ] **Step 7: 커밋 (사용자에게 제안)**

`git add web/src/lib/admin.ts web/src/pages/admin/AdminUsers.tsx`

```
기능: 사용자 관리 화면에 잠금 표시·해제 버튼 추가
```

---

## Self-Review 결과

- **스펙 커버리지:** 2장(모델·설정·마이그레이션) → Task 1 / 3장(로그인 흐름·423) → Task 2 / 4장(쿼리) → Task 1(SELECT)·Task 2·3(쓰기) / 5장(unlock API) → Task 3 / 6장(프론트) → Task 4 / 7장(검증) → Task 1·2·3 pytest + Task 4 수동. 비범위(자동 해제, 감사 테이블, IP 잠금)는 어떤 태스크에도 없다.
- **타입 일관성:** `failed_login_count`/`locked_at`/`unlocked_at` 이름이 모델·쿼리·프론트에서 동일. `Errors.locked`(Task 2)·`unlock_user`(Task 3) 시그니처가 소비처와 일치. 프론트 `adminUsers.unlock`(Task 4 Step 1)을 `act`(Step 2)가 `adminUsers[action]`으로 호출.
- **플레이스홀더 없음:** 모든 코드 단계에 실제 코드. 백엔드는 TDD(RED→GREEN), 프론트는 러너 부재로 lint+build+수동.
- **보안 불변식 확인:** 오답 경로는 잠김 여부와 무관하게 통일 401(Task 2 Step 5), 더미 해시 유지, 단축 평가 미사용.
