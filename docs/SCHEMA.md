# 데이터베이스 스키마

현재 실제로 존재하는 테이블만 정리한 문서. 실제 소스(`app/models/*.py`)와 Alembic 마이그레이션이 기준(source of truth)이며, 이 문서는 그걸 사람이 보기 편하게 요약한 것이다. **테이블을 추가/변경하는 Task를 끝낼 때마다 이 문서도 같이 갱신한다.**

설계 의도(왜 이런 규칙인지)는 `docs/superpowers/specs/2026-07-09-studio-design.md`의 "3. 데이터 모델" 절 참고. 여기는 "지금 DB에 뭐가 있는지"만 다룬다 — 스펙에는 있지만 아직 구현 안 된 테이블(Project/Stage/Asset 등)은 포함하지 않는다.

실행 가능한 형태의 DDL(CREATE TABLE + COMMENT ON)은 `docs/schema.sql` 참고 — 이 문서와 같은 내용을 SQL 원문으로 정리한 것이며, 테이블이 바뀔 때 둘 다 같이 갱신한다.

## 공통 컬럼 (모든 테이블 — `BaseEntity` 상속)

`app/models/base.py`

| 컬럼 | 타입 | Null | 기본값 | 설명 |
|---|---|---|---|---|
| `id` | BIGINT | NOT NULL | 자동 증가(IDENTITY) | PK |
| `created_at` | TIMESTAMP(tz 없음) | NOT NULL | `timezone('Asia/Seoul', now())` (DB 기본값) | 생성일시, 로컬 벽시계 시각(Asia/Seoul, naive) |
| `updated_at` | TIMESTAMP(tz 없음) | NOT NULL | `timezone('Asia/Seoul', now())` (DB 기본값), 수정 시 동일 표현식으로 갱신 | 수정일시 |
| `created_by` | BIGINT | NULL 허용 | 없음 | 생성자. 테이블마다 FK 대상이 달라 `BaseEntity`엔 FK 없음(테이블별로 재선언해서 FK 추가) |
| `updated_by` | BIGINT | NULL 허용 | 없음 | 수정자 |

`created_at`/`updated_at`은 원래 애플리케이션(Python) `now_local()`이 채웠으나, DB 레벨 기본값(`DEFAULT`)으로 전환했다. DB 세션 타임존이 UTC일 수 있어(로컬 개발용 Postgres 컨테이너 등) 그냥 `now()`를 쓰면 로컬시간 저장 규칙이 깨지므로, `timezone('Asia/Seoul', now())`로 명시적 변환한다. 단, 이 표현식은 DB SQL이라 `APP_TIMEZONE` 설정(런타임)을 반영하지 않고 항상 Asia/Seoul로 고정된다 — `now_local()` 유틸(`app/utils/time.py`)은 여전히 존재하며 업무 코드(aiosql insert 등)에서 명시적으로 값을 채울 때 계속 쓰인다.

## users

`app/models/user.py` — Alembic: `alembic/versions/26e94d5983ab_create_users_table.py`

| 컬럼 | 타입 | Null | 기본값 | 제약 |
|---|---|---|---|---|
| `id` / `created_at` / `updated_at` | — | — | — | `BaseEntity` 공통 컬럼 |
| `created_by` | BIGINT | NULL 허용 | 없음 | FK → `users.id` (자기참조) |
| `updated_by` | BIGINT | NULL 허용 | 없음 | FK → `users.id` (자기참조) |
| `email` | VARCHAR | NOT NULL | 없음 | UNIQUE, INDEX |
| `password_hash` | VARCHAR | NOT NULL | 없음 | argon2 해시(평문 저장 금지) |
| `role` | VARCHAR | NOT NULL | `"member"` | `member` \| `admin` |
| `status` | VARCHAR | NOT NULL | `"pending"` | `pending` \| `active` \| `disabled` \| `rejected` |
| `approved_at` | TIMESTAMP(tz 없음) | NULL 허용 | 없음 | 승인/거절 처리 시각 |
| `approved_by` | BIGINT | NULL 허용 | 없음 | FK → `users.id` (승인/거절한 관리자) |

`created_by`/`updated_by`는 `BaseEntity`를 그대로 물려받지 않고 `users.id` FK를 붙여 재선언되어 있다(다른 테이블이 이 패턴을 따를 때도 동일하게 재선언 필요).

## refresh_tokens

`app/models/refresh_token.py` — Alembic: `alembic/versions/6e54c5b37edf_create_refresh_tokens_table.py`

| 컬럼 | 타입 | Null | 기본값 | 제약 |
|---|---|---|---|---|
| `id` / `created_at` / `updated_at` | — | — | — | `BaseEntity` 공통 컬럼 |
| `created_by` | BIGINT | NULL 허용 | 없음 | FK 없음 (`BaseEntity` 그대로) |
| `updated_by` | BIGINT | NULL 허용 | 없음 | FK 없음 (`BaseEntity` 그대로) |
| `user_id` | INTEGER | NOT NULL | 없음 | FK → `users.id`, INDEX |
| `token_hash` | VARCHAR | NOT NULL | 없음 | UNIQUE, INDEX — SHA-256 해시값(원문 저장 안 함) |
| `expires_at` | TIMESTAMP(tz 없음) | NOT NULL | 없음 | 만료 일시 |
| `revoked_at` | TIMESTAMP(tz 없음) | NULL 허용 | 없음 | 폐기(회전/로그아웃) 처리 일시, 미폐기 시 NULL |

`user_id`는 모델에서 `int`(별도 `sa_type` 지정 없음)로 선언되어 SQLModel이 `INTEGER`로 매핑한다 — `users.id`(BIGINT)를 참조하는 FK지만 컬럼 타입 자체는 BIGINT가 아니다(Plan 2 Task 3 브리프의 명시된 코드를 그대로 따름). PostgreSQL은 int4/int8 간 FK 제약을 허용하므로 동작에는 문제가 없지만, 향후 매우 큰 `user_id` 값이 필요할 가능성이 있다면 `BigInteger`로 맞추는 것을 고려할 것.

## 지운 테이블

- `error_codes` — 에러 코드를 DB 카탈로그로 관리하던 초기 설계의 잔재. 소스 관리 방식(`AppError`/`Errors`)으로 전환하며 삭제됨 (`alembic/versions/f1515bf03a82_drop_error_codes_table_error_handling_.py`).
