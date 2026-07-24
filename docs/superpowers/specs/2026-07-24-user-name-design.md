# 사용자 이름(users.name) — 설계 문서 (Design Spec)

- **작성일:** 2026-07-24
- **대상:** `users` 테이블에 표시용 이름 추가, 상단바·관리자 목록에서 이메일 대신 이름 표시
- **상위 문서:** [2026-07-09-studio-design.md](2026-07-09-studio-design.md) (전체 설계)

---

## 1. 목표 & 범위

### 목표
사용자를 이메일로만 식별하던 화면을 **사람이 읽는 이름**으로 바꾼다. 상단바가 `dev@bluenmobile.com · ADMIN` 대신 `홍길동 · ADMIN`을 보여주고, 관리자가 가입 승인·사용자 관리를 할 때 이메일과 이름을 함께 본다.

### 확정된 결정 (브레인스토밍)
| 항목 | 결정 | 이유 |
|------|------|------|
| 필수 여부 | **NOT NULL (필수)** | 화면에 폴백 분기(`name ?? email`)가 여러 곳 생기는 걸 막는다. 이름이 항상 있으면 표시 코드가 단순하다 |
| 입력 시점 | **회원가입 폼** | 자율 가입이므로 본인이 적는 게 자연스럽다. 관리자가 대신 채우는 경로는 만들지 않는다 |
| 기존 행 백필 | **이메일의 `@` 앞부분** | `dev@bluenmobile.com` → `dev`. 이메일 전체보다 이름답고, 나중에 사람이 고치기 쉽다 |
| 유니크 제약 | **없음** | 동명이인을 막을 이유가 없다. 식별자는 여전히 이메일이다 |
| 표시 범위 | **상단바 + 관리자 사용자 목록** | 관리자가 승인 판단할 때 이메일만 보는 것보다 낫다 |

### 비범위 (YAGNI)
- 설정 화면에서 이름 변경 — 설정 화면 자체가 아직 자리표시자다
- 관리자가 남의 이름을 수정하는 기능
- 이름 검색·정렬
- 프로필 이미지·닉네임 등 추가 프로필 필드

---

## 2. 데이터베이스

Alembic 마이그레이션 1개. **NULL로 추가 → 백필 → NOT NULL 승격** 3단계여야 기존 행이 있어도 실패하지 않는다.

```sql
-- upgrade
ALTER TABLE users ADD COLUMN name VARCHAR NULL;
UPDATE users SET name = split_part(email, '@', 1);
ALTER TABLE users ALTER COLUMN name SET NOT NULL;

-- downgrade
ALTER TABLE users DROP COLUMN name;
```

- `split_part`는 PostgreSQL 내장 함수다(이 프로젝트는 Postgres 전용이라 문제없다).
- 컬럼 코멘트: `"표시용 이름 (로그인 식별자는 email)"` — 기존 모델의 코멘트 관례를 따른다.
- 길이 제약은 DB가 아니라 애플리케이션에서 검증한다(기존 `email`·`password_hash`도 VARCHAR 무제한).

---

## 3. 백엔드

### 3.1 모델 (`app/models/user.py`)
`email` 바로 아래에 추가한다.

```python
name: str = Field(default="", sa_column_kwargs={"comment": "표시용 이름 (로그인 식별자는 email)"})
```

**`default=""`를 두는 이유 (계획 수립 중 확정):** 테스트 18개 파일이 `User(...)`를 29번 생성하는데, 기본값이 없으면 전부 NOT NULL 위반으로 깨진다. 이 기능과 무관한 파일들이다.

이 기본값이 안전한 근거는 **프로덕션 쓰기 경로가 모델이 아니라는 것**이다 — 회원가입은 raw SQL `insert_user`를 쓰고(3.2), 거기서 `name`을 명시적 파라미터로 받으므로 빈 이름이 API 경로로 들어올 수 없다. DB는 양쪽 모두 NOT NULL을 유지한다.

### 3.2 쿼리 (`app/queries/users.sql`)
| 쿼리 | 변경 |
|------|------|
| `find_by_email^` | SELECT에 `name` 추가 |
| `find_by_id^` | SELECT에 `name` 추가 |
| `list_by_status` | SELECT에 `name` 추가 |
| `insert_user<!` | 컬럼·파라미터에 `name` 추가 |

### 3.3 API (`app/auth/router.py`)
- `RegisterRequest`에 `name: str` 추가
- 회원가입 처리에서 `name = body.name.strip()` 후 검증 → `insert_user`에 전달
- **응답 2곳**에 `name`을 명시적으로 추가: 로그인([router.py:144](../../../app/auth/router.py)), `/auth/me`([:209](../../../app/auth/router.py)). 두 곳 모두 `{"id":..., "email":..., "role":...}`를 손으로 조립하므로 키를 직접 넣어야 한다.
- **관리자 목록은 수정이 필요 없다** — [admin_router.py:22](../../../app/auth/admin_router.py)가 `dict(row)`로 행 전체를 그대로 내보내므로, 3.2에서 `list_by_status`의 SELECT에 `name`을 넣으면 응답에 자동으로 실린다.

### 3.4 검증
`strip()` 후 **1~50자**. 위반 시 `AppError(400, "INVALID_NAME", "이름은 1~50자로 입력해 주세요.")`.

- 공백만 입력 → 길이 0 → 거부
- 이메일과 달리 소문자 변환·유니크 검사를 하지 않는다

### 3.5 샘플 데이터 (`app/auth/seed_sample_users.py`)
개발용 샘플 8명에 한국어 이름을 부여한다. 이름이 NOT NULL이 되었으므로 값을 주지 않으면 시드가 깨진다.

---

## 4. 프론트엔드

| 위치 | 변경 |
|------|------|
| `lib/auth.tsx` | `User` 타입에 `name: string`, `register(email, password, name)` 시그니처 확장 |
| `pages/Register.tsx` | 이름 입력 필드 추가(이메일 위). 기존 `TextField` 컴포넌트 재사용 |
| `components/layout/UserMenu.tsx` | `{user?.email}` → `{user?.name}` |
| `pages/admin/AdminUsers.tsx` | `AdminUser` 타입에 `name`, 이메일 **앞**에 이름 컬럼 |

관리자 목록의 이름 컬럼은 이메일과 같은 좌측정렬을 쓴다(사람 이름은 길이가 제각각이라 중앙정렬이 어울리지 않는다).

---

## 5. 테스트

| 대상 | 방식 |
|------|------|
| 마이그레이션 | 기존 `tests/test_alembic_migration.py` 패턴으로 upgrade/downgrade 왕복. **기존 행이 있는 상태에서 백필이 동작하는지**가 핵심 — 사용자를 먼저 넣고 마이그레이션을 돌린다 |
| 회원가입 | 이름이 저장되는지, 앞뒤 공백이 잘리는지 |
| 이름 검증 | 빈 문자열·공백만·51자 → `INVALID_NAME` 400 |
| 로그인 / `/auth/me` | 응답에 `name`이 실리는지 |
| 관리자 목록 | 응답에 `name`이 실리는지 (라우터 무수정이라 SELECT 변경만으로 통과해야 한다 — 이 테스트가 그 배선을 고정한다) |
| 기존 테스트 | 회원가입을 호출하는 모든 테스트가 `name`을 넘기도록 수정해야 한다 — **누락하면 422로 무더기 실패**한다 |

프론트는 테스트 러너가 없으므로 `npm run build`(tsc) + `npm run lint`로 검증한다.

---

## 6. 구현 중 주의할 점

1. **기존 테스트의 회원가입 호출부** — `POST /auth/register`에 필수 필드가 늘어난다. 실측 결과 `tests/test_auth_register.py` **한 파일에서 5곳**뿐이다(다른 테스트는 `User` 모델을 직접 만든다). 그 모델 경로는 3.1의 `default=""`가 흡수하므로 추가 수정이 없다.
2. **시드 스크립트** — NOT NULL이라 이름 없이 INSERT하면 실패한다. 3.5를 빠뜨리지 말 것.
3. **`login` 응답 재사용** — 프론트는 로그인 응답을 그대로 `User`로 쓴다(`/auth/me`를 다시 부르지 않는다). 로그인 응답에 `name`이 빠지면 상단바가 비므로 두 응답 모두 확인한다.
4. **백필 결과** — 관리자 계정이 `dev`로 보인다. 사용자가 원하면 DB에서 직접 고친다(별도 UI 없음).
