# 공통코드 값 대문자 통일 설계 (Design Spec)

- **작성일:** 2026-07-13
- **한 줄 요약:** DB에 저장되는 공통코드 값(`role`, `status`)을 대문자로 통일하고, 흩어진 문자열 리터럴을 Enum 한 곳으로 모은다.
- **상위 설계:** `docs/superpowers/specs/2026-07-09-studio-design.md`

---

## 1. 배경 & 목표

### 문제
현재 코드값이 **소문자 문자열 리터럴**로 12개 파일에 흩어져 있다.

| 컬럼 | 현재 값 |
|------|---------|
| `users.role` | `member`, `admin` |
| `users.status` | `pending`, `active`, `disabled`, `rejected` |

사용처: `app/models/user.py`(기본값·컬럼 코멘트), `app/auth/router.py`(가입/로그인/갱신), `app/auth/dependencies.py`, `app/auth/admin_router.py`, `app/auth/seed_admin.py`, `web/src/lib/auth.tsx`(타입), 그리고 테스트 7개 파일.

오타(`"actve"`)가 타입 검사도 임포트도 통과해 런타임까지 살아남는다. 앞으로 `Project.status`, `Stage.status`·`Stage.name`, `Asset.kind`가 추가되면 같은 문제가 그대로 반복된다.

### 목표
1. 코드값을 **대문자로 통일**한다 (`ACTIVE`, `ADMIN`, …).
2. 값의 정의를 **한 곳(Enum)** 에 모아, 코드가 리터럴 대신 상수를 쓰게 한다.
3. 기존 DB 데이터를 **마이그레이션으로 변환**한다.

### 범위
- **DB 저장값 · API 응답 · API 쿼리 파라미터 · 프론트 타입을 모두 대문자로.** 경계에서 변환하는 계층을 두지 않는다 — 변환 계층은 빼먹으면 조용히 깨지고, 어디서 보든 같은 값이어야 디버깅이 쉽다.
- 대상 코드값은 **`users.role`과 `users.status`뿐**이다. 아직 존재하지 않는 `Project`/`Stage`/`Asset`의 코드값은 이번 범위가 아니며, 그 모델을 만들 때 같은 규칙(대문자 + Enum)을 따른다.

### 비범위 (YAGNI)
- DB CHECK 제약 — 값 추가 때마다 마이그레이션이 필요해진다. Enum + FastAPI 검증으로 앱 경계에서 막는 것으로 충분하다.
- 공통코드 **테이블**(코드 마스터) — 상위 설계가 에러 코드를 DB로 관리하지 않기로 한 것과 같은 이유. 값의 출처는 소스 코드다.
- 화면의 한글 라벨링(`ADMIN` → "관리자") — 대시보드는 role을 그대로 표시한다. 라벨은 화면이 늘어날 때 별도로 다룬다.

---

## 2. 코드값 정의 — `app/constants.py` (신규)

Python 3.12의 `StrEnum`을 쓴다.

```python
from enum import StrEnum


class UserRole(StrEnum):
    MEMBER = "MEMBER"
    ADMIN = "ADMIN"


class UserStatus(StrEnum):
    PENDING = "PENDING"
    ACTIVE = "ACTIVE"
    DISABLED = "DISABLED"
    REJECTED = "REJECTED"
```

**왜 `StrEnum`인가:** 멤버가 `str`의 하위 타입이라 평범한 문자열과 그대로 비교되고(`row["status"] != UserStatus.ACTIVE` — aiosql이 돌려주는 값은 순수 `str`이다), JSON 직렬화 시 값(`"ACTIVE"`)으로 나가며, SQLModel 컬럼 기본값으로도 문자열처럼 동작한다. 별도의 변환·역직렬화 코드가 필요 없다.

**왜 `app/constants.py`인가:** 이 파일은 아무것도 import하지 않는다. 따라서 모델·라우터·의존성·시드 어디서 가져다 써도 순환 참조가 생기지 않는다. 앞으로 추가될 `ProjectStatus`, `StageName`, `StageStatus`, `AssetKind`도 여기에 모인다.

---

## 3. 백엔드 치환

리터럴을 상수로 바꾼다. 값 자체가 소문자 → 대문자로 바뀐다.

| 파일 | 변경 |
|------|------|
| `app/models/user.py` | `role` 기본값 `UserRole.MEMBER`, `status` 기본값 `UserStatus.PENDING`. 컬럼 코멘트의 값 표기도 대문자로 (`권한: MEMBER \| ADMIN`) |
| `app/auth/router.py` | 가입 시 `role=UserRole.MEMBER`, `status=UserStatus.PENDING`, 응답 `{"status": UserStatus.PENDING}` / 로그인·갱신의 `status != UserStatus.ACTIVE` 비교 |
| `app/auth/dependencies.py` | `current_user`의 `status != UserStatus.ACTIVE`, `require_admin`의 `role != UserRole.ADMIN` |
| `app/auth/admin_router.py` | approve → `UserStatus.ACTIVE`, reject → `UserStatus.REJECTED`, 쿼리 파라미터 타입을 `UserStatus`로 |
| `app/auth/seed_admin.py` | `role=UserRole.ADMIN`, `status=UserStatus.ACTIVE` |

### 덤: 쿼리 파라미터 검증이 공짜로 생긴다

```python
async def list_users(status: UserStatus = Query(UserStatus.PENDING), ...):
```

FastAPI가 Enum 타입을 검증하므로 `/admin/users?status=nonsense`는 **422**로 거절된다. Plan 2 리뷰에서 "status 파라미터 값 미검증"으로 남겨뒀던 Minor가 여기서 해소된다.

---

## 4. API 계약 & 프론트

변경되는 계약:

| 대상 | 이전 | 이후 |
|------|------|------|
| `GET /auth/me`, `POST /auth/login` 응답의 `role` | `"member"` | `"MEMBER"` |
| `POST /auth/register` 응답의 `status` | `"pending"` | `"PENDING"` |
| `GET /admin/users` 응답의 `role`·`status` | 소문자 | 대문자 |
| `GET /admin/users?status=` | `pending` | `PENDING` |

프론트 변경은 `web/src/lib/auth.tsx`의 타입 한 줄뿐이다.

```ts
export type User = {
  id: number
  email: string
  role: 'MEMBER' | 'ADMIN'
}
```

프론트에는 role 값을 비교하는 로직이 아직 없다(라우트 가드는 로그인 여부만 본다). `Dashboard`가 `user.role`을 그대로 출력하므로 화면에 `ADMIN`으로 표시된다 — 의도된 동작이며, 한글 라벨은 비범위다.

---

## 5. 마이그레이션 (Alembic 리비전 1개)

`role`/`status`의 기본값은 **DB가 아니라 앱 계층**에 있다(`app/models/user.py`의 `Field(default=...)`, `server_default` 아님). 따라서 스키마 변경은 없고 **데이터와 컬럼 코멘트만** 바꾼다.

```python
def upgrade():
    op.execute("UPDATE users SET role = upper(role), status = upper(status)")
    op.alter_column("users", "role", comment="권한: MEMBER | ADMIN (기본값 MEMBER)", existing_type=sa.String())
    op.alter_column("users", "status", comment="가입 상태: PENDING | ACTIVE | DISABLED | REJECTED (기본값 PENDING)", existing_type=sa.String())

def downgrade():
    op.execute("UPDATE users SET role = lower(role), status = lower(status)")
    # 코멘트도 소문자 표기로 원복
```

`upper()`는 이미 대문자인 값에 대해 멱등하므로 재실행해도 안전하다.

### 함께 처리하는 스키마 문서 — `SCHEMA.md` 삭제, `schema.sql`로 일원화

스키마 문서가 둘(`docs/SCHEMA.md`, `docs/schema.sql`)이라 같은 내용을 두 곳에 적고 있고, 둘 다 코드값을 소문자로 적고 있다. 갱신할 곳이 둘이면 하나는 언젠가 뒤처진다. **`SCHEMA.md`를 삭제하고 `schema.sql` 하나로 일원화한다.**

`SCHEMA.md`의 컬럼 표는 `schema.sql`의 DDL과 중복이므로 그냥 사라진다. 다만 **DDL에 담기지 않는 고유한 설명 두 가지는 `schema.sql` 상단 주석으로 옮긴다** — 지우면 "왜 이렇게 했더라"가 다시 반복되는 내용이다.

| 옮길 내용 | 왜 필요한가 |
|-----------|-------------|
| 테이블 생성 규칙 (`id` → 업무 컬럼 → 감사 컬럼) 과 그 근거 | 감사 컬럼 4개를 `BaseEntity` 믹스인에 넣지 않고 `*_field()` 헬퍼로 각 테이블이 직접 선언하는 이유(믹스인 컬럼은 항상 서브클래스 업무 컬럼보다 앞에 와서 컬럼 순서 규칙을 지킬 수 없다). 직전 커밋의 핵심 근거다. |
| `error_codes` 삭제 이력 | 에러 처리를 DB 카탈로그에서 소스 관리(`AppError`/`Errors`)로 바꾼 결정의 흔적. 마이그레이션 체인에 생성·삭제가 모두 남아 있어 이력을 모르면 혼란스럽다. |

`schema.sql` 상단의 "이 파일과 `docs/SCHEMA.md`를 함께 갱신한다"는 문구도 함께 정리한다(갱신 대상이 이 파일 하나가 된다).

**대문자 반영:** `schema.sql`의 `COMMENT ON COLUMN users.role` / `users.status` 값 표기를 대문자로 고친다 (`member | admin` → `MEMBER | ADMIN`, `pending | active | disabled | rejected` → `PENDING | ACTIVE | DISABLED | REJECTED`).

**순서 주의:** 문서 갱신은 **마이그레이션과 같은 커밋**에서 한다. 문서를 먼저 고치면 실제 DB와 어긋나는 기간이 생긴다.

### 배포 시 주의 (기록용)
`current_user`(`app/auth/dependencies.py`)는 JWT의 `role` 클레임을 읽지 않는다. 토큰에서는 `payload["sub"]`만 꺼내고, `role`·`status`는 그때마다 DB 행을 다시 읽어서 판단한다. `require_admin`이 비교하는 `user["role"]`도 이 DB 행에서 온 값이다. 따라서 **이미 발급된 토큰이 이 배포로 무효화되는 일은 없다.**

진짜 위험은 **코드와 마이그레이션의 순서**다. 대문자 변환은 데이터 마이그레이션이고, 비교 코드는 대소문자를 그대로 비교하므로(`row["status"] != UserStatus.ACTIVE`) 코드와 DB의 대소문자가 어긋나면 관리자뿐 아니라 **전체 사용자**가 인증에서 막힌다.

- **구 코드 + 마이그레이션 적용된 DB:** `row["status"]`는 `"ACTIVE"`인데 구 코드는 `"active"`와 비교한다 → 모든 사용자에서 `!=`가 참이 된다. `login`은 403, `current_user`는 401, `refresh`도 401 — 인증 전면 중단.
- **신 코드 + 마이그레이션 안 된 DB:** 위와 대칭인 상황이 그대로 재현된다.
- **`downgrade()`만 실행하고 코드는 되돌리지 않는 경우**도 동일하게 인증 전면 중단을 일으킨다.

**운영 규칙:** API를 내린 뒤 마이그레이션하고, 새 코드로 올린다. 구 코드가 떠 있는 채로 마이그레이션하지 않는다. 롤백 방향도 같은 제약을 받는다 — 코드와 마이그레이션은 항상 같이 되돌린다.

---

## 6. 테스트

### 갱신
테스트 7개 파일의 소문자 리터럴을 `app/constants.py`의 Enum 상수로 바꾼다. 값이 바뀌었으므로 리터럴을 그대로 두면 실패한다 — 이것이 곧 회귀 검증이다.

- `tests/test_user_model.py` — 기본값이 `UserRole.MEMBER` / `UserStatus.PENDING`
- `tests/test_auth_register.py` — 응답 `status == UserStatus.PENDING`
- `tests/test_auth_login.py` · `test_auth_refresh_logout.py` · `test_auth_dependencies.py` · `test_auth_me.py` · `test_admin_users.py` · `test_seed_admin.py` · `test_security.py`

### 신규
- `tests/test_admin_users.py` — `GET /admin/users?status=nonsense` → **422** (Enum 검증)

### 만들지 않는 것
데이터 마이그레이션 전용 테스트는 만들지 않는다. 변환은 일회성 `upper()` SQL 한 줄이고, 기존 `tests/test_alembic_migration.py`가 마이그레이션 체인 전체가 빈 DB에 깨끗이 적용되는지는 이미 검증한다. 실제 데이터 변환은 로컬 DB에서 `upgrade head` 후 눈으로 확인한다.

---

## 7. 검증 방법

1. `npm test` — 백엔드 전체 통과 (현재 72개 + 신규 1개)
2. `npm run build` — 프론트 TypeScript 컴파일 통과
3. 로컬 DB 마이그레이션 확인:
   ```
   uv run alembic upgrade head
   docker compose exec db psql -U studio -d studio -c "SELECT email, role, status FROM users;"
   ```
   → 기존 admin 계정이 `ADMIN` / `ACTIVE`로 바뀌어 있어야 한다.
4. 브라우저: 재로그인 후 대시보드에 `ADMIN`이 표시되고, 관리자 기능이 정상 동작한다.
