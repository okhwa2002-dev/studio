# 데이터베이스 스키마

현재 실제로 존재하는 테이블만 정리한 문서. 실제 소스(`app/models/*.py`)와 Alembic 마이그레이션이 기준(source of truth)이며, 이 문서는 그걸 사람이 보기 편하게 요약한 것이다. **테이블을 추가/변경하는 Task를 끝낼 때마다 이 문서도 같이 갱신한다.**

설계 의도(왜 이런 규칙인지)는 `docs/superpowers/specs/2026-07-09-studio-design.md`의 "3. 데이터 모델" 절 참고. 여기는 "지금 DB에 뭐가 있는지"만 다룬다 — 스펙에는 있지만 아직 구현 안 된 테이블(Project/Stage/Asset 등)은 포함하지 않는다.

실행 가능한 형태의 DDL(CREATE TABLE + COMMENT ON)은 `docs/schema.sql` 참고 — 이 문서와 같은 내용을 SQL 원문으로 정리한 것이며, 테이블이 바뀔 때 둘 다 같이 갱신한다.

## 테이블 생성 규칙 (컬럼 순서: `id`, 업무 컬럼, 생성/수정 감사 컬럼)

`app/models/base.py`

모든 테이블은 컬럼이 **`id` → 업무 컬럼들 → `created_at`/`created_by`/`updated_at`/`updated_by`** 순서로 정렬된다. `BaseEntity`는 `id`만 제공하는 믹스인이다 — Python/SQLAlchemy 상속 규칙상 믹스인 컬럼은 항상 서브클래스가 선언한 업무 컬럼보다 앞에 오기 때문에, 감사 컬럼까지 `BaseEntity`에 넣으면 "업무 컬럼 뒤에 감사 컬럼" 순서를 만들 수 없다. 그래서 감사 컬럼 4개는 `app/models/base.py`의 재사용 가능한 헬퍼 함수로만 설정 로직을 한 곳에서 관리하고, 각 테이블이 자기 클래스 본문 맨 아래에서 명시적으로 호출해 선언한다.

| 헬퍼 | 컬럼 | 타입 | Null | 기본값 |
|---|---|---|---|---|
| `BaseEntity.id` | `id` | BIGINT | NOT NULL | 자동 증가(IDENTITY) — PK |
| `created_at_field()` | `created_at` | TIMESTAMP(tz 없음) | NOT NULL | `timezone('Asia/Seoul', now())` (DB 기본값) |
| `created_by_field(foreign_key=None, comment=...)` | `created_by` | BIGINT | NULL 허용 | 없음 (FK는 테이블마다 다르므로 호출 시 지정) |
| `updated_at_field()` | `updated_at` | TIMESTAMP(tz 없음) | NOT NULL | `timezone('Asia/Seoul', now())` (DB 기본값), 수정 시 동일 표현식으로 갱신 |
| `updated_by_field(foreign_key=None, comment=...)` | `updated_by` | BIGINT | NULL 허용 | 없음 |

`created_at`/`updated_at`은 원래 애플리케이션(Python) `now_local()`이 채웠으나, DB 레벨 기본값(`DEFAULT`)으로 전환했다. DB 세션 타임존이 UTC일 수 있어(로컬 개발용 Postgres 컨테이너 등) 그냥 `now()`를 쓰면 로컬시간 저장 규칙이 깨지므로, `timezone('Asia/Seoul', now())`로 명시적 변환한다. 단, 이 표현식은 DB SQL이라 `APP_TIMEZONE` 설정(런타임)을 반영하지 않고 항상 Asia/Seoul로 고정된다 — `now_local()` 유틸(`app/utils/time.py`)은 여전히 존재하며 업무 코드(aiosql insert 등)에서 명시적으로 값을 채울 때 계속 쓰인다.

## users

`app/models/user.py` — Alembic: `alembic/versions/6b5040798a90_recreate_users_table_with_business_then_.py`

| 컬럼 순서 | 컬럼 | 타입 | Null | 기본값 | 제약 |
|---|---|---|---|---|---|
| 1 | `id` | — | — | — | `BaseEntity` PK |
| 2 | `email` | VARCHAR | NOT NULL | 없음 | UNIQUE, INDEX |
| 3 | `password_hash` | VARCHAR | NOT NULL | 없음 | argon2 해시(평문 저장 금지) |
| 4 | `role` | VARCHAR | NOT NULL | `"member"` | `member` \| `admin` |
| 5 | `status` | VARCHAR | NOT NULL | `"pending"` | `pending` \| `active` \| `disabled` \| `rejected` |
| 6 | `approved_at` | TIMESTAMP(tz 없음) | NULL 허용 | 없음 | 승인/거절 처리 시각 |
| 7 | `approved_by` | BIGINT | NULL 허용 | 없음 | FK → `users.id` (승인/거절한 관리자) |
| 8 | `created_at` | — | — | — | `created_at_field()` |
| 9 | `created_by` | BIGINT | NULL 허용 | 없음 | FK → `users.id` (자기참조, `created_by_field(foreign_key="users.id", ...)`) |
| 10 | `updated_at` | — | — | — | `updated_at_field()` |
| 11 | `updated_by` | BIGINT | NULL 허용 | 없음 | FK → `users.id` (자기참조, `updated_by_field(foreign_key="users.id", ...)`) |

## refresh_tokens

`app/models/refresh_token.py` — Alembic: `alembic/versions/6b5040798a90_recreate_users_table_with_business_then_.py`

| 컬럼 순서 | 컬럼 | 타입 | Null | 기본값 | 제약 |
|---|---|---|---|---|---|
| 1 | `id` | — | — | — | `BaseEntity` PK |
| 2 | `user_id` | BIGINT | NOT NULL | 없음 | FK → `users.id`, INDEX |
| 3 | `token_hash` | VARCHAR | NOT NULL | 없음 | UNIQUE, INDEX — SHA-256 해시값(원문 저장 안 함) |
| 4 | `expires_at` | TIMESTAMP(tz 없음) | NOT NULL | 없음 | 만료 일시 |
| 5 | `revoked_at` | TIMESTAMP(tz 없음) | NULL 허용 | 없음 | 폐기(회전/로그아웃) 처리 일시, 미폐기 시 NULL |
| 6 | `created_at` | — | — | — | `created_at_field()` |
| 7 | `created_by` | BIGINT | NULL 허용 | 없음 | FK 없음 (`created_by_field()`, foreign_key 미지정) |
| 8 | `updated_at` | — | — | — | `updated_at_field()` |
| 9 | `updated_by` | BIGINT | NULL 허용 | 없음 | FK 없음 (`updated_by_field()`, foreign_key 미지정) |

`user_id`는 `sa_type=BigInteger`로 선언되어 `users.id`(BIGINT)와 동일한 타입의 FK 컬럼이다.

## 지운 테이블

- `error_codes` — 에러 코드를 DB 카탈로그로 관리하던 초기 설계의 잔재. 소스 관리 방식(`AppError`/`Errors`)으로 전환하며 삭제됨 (`alembic/versions/f1515bf03a82_drop_error_codes_table_error_handling_.py`).
