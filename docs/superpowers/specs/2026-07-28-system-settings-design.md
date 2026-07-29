# 시스템 설정 설계

- 작성일: 2026-07-28
- 범위: 관리자 시스템 설정 (테이블 · 런타임 설정 계층 · API · 화면)

## 1. 목적과 범위

지금 운영 값은 전부 `.env`에 있다(`app/config.py`). 스크립트 provider를 바꾸거나 로그인 잠금 횟수를 조정하려면 파일을 고치고 재배포·재시작해야 한다. `/admin/system` 라우트와 사이드바 메뉴는 이미 뚫려 있지만 화면은 `Placeholder`다.

관리자가 화면에서 값을 바꾸면 재시작 없이 반영되는 설정 계층을 만든다.

**하는 것**

- 파이프라인 기본값: 단계별 provider, Whisper 모델, 렌더 배경색·폰트·크기, 스톡 소스 우선순위·상한·타임아웃
- 계정/보안 정책: 로그인 실패 잠금 횟수, 비밀번호 최소 길이, 가입 자동 승인
- 회원가입 비밀번호 길이 검증 추가 (현재 공백 — 3절 참고)

**하지 않는 것**

- 외부 API 키 관리(OpenAI·Anthropic·Pexels·Pixabay) — 비밀값을 DB에 넣는 문제라 암호화·마스킹·감사를 따로 설계해야 한다. `.env`에 남긴다.
- 시스템 상태 진단 화면(워커 큐·스토리지 사용량·ffmpeg 설치 여부) — 설정이 아니라 진단이다. 별도 작업.
- `DATABASE_URL`·`JWT_SECRET`·`CORS_ORIGINS`·`SECURE_COOKIES`·`LOG_DIR`·`STORAGE_PATH` — 부팅에 필요하거나 파일시스템·보안에 직결된다. `.env` 고정.
- `WORKER_CONCURRENCY` — 워커 스레드풀 크기라 이미 뜬 워커에 런타임 변경이 의미가 없다.

## 2. 데이터 모델

### 2-1. `system_settings`

| 컬럼 | 타입 | 설명 |
|---|---|---|
| `id` | BIGINT PK | 기본키, BIGINT 자동 증가 |
| `key` | VARCHAR NOT NULL UNIQUE | 설정 키 (`RuntimeSettings` 필드명과 1:1) |
| `value` | TEXT NOT NULL | 설정값 (문자열 직렬화 — 파싱·검증은 앱이 담당) |
| `created_at` / `created_by` | | `base.py` 헬퍼 |
| `updated_at` / `updated_by` | | `base.py` 헬퍼 |

컬럼 순서는 프로젝트 규칙대로 `id` → 업무 컬럼 → 감사 컬럼이다. 모델은 `app/models/system_setting.py`에 `BaseEntity`를 상속해 선언하고, 감사 컬럼은 클래스 본문 맨 아래에서 `created_at_field()` 등 헬퍼로 명시 선언한다.

**이 테이블은 "관리자가 바꾼 값"만 담는다.** 전체 설정 목록을 시드하지 않는다. 키가 없으면 `.env` 값이 그대로 유효값이 된다. 이 선택이 이 설계의 중심이다.

- 마이그레이션에 시드 데이터가 필요 없다. 기존 배포는 테이블이 빈 채로 지금과 동일하게 동작한다 — 회귀 위험이 사실상 없다.
- 설정 항목을 추가할 때 마이그레이션이 생기지 않는다. `RuntimeSettings`에 필드 한 줄이면 된다. 나중에 API 키·서비스명 같은 항목을 붙일 때 비용이 들지 않는다.
- 관리자가 값을 기본값으로 되돌리면 행을 **삭제**한다. 그래야 "`.env`를 바꾸면 따라온다"는 성질이 유지된다. 기본값과 같은 값을 행으로 남기면 그 키만 `.env` 변경에 반응하지 않게 되어 원인 찾기 어려운 불일치가 생긴다.

**값을 TEXT 하나로 두고 타입을 DB에 두지 않는다.** 컬럼형(한 행에 항목마다 컬럼)이 타입 안전하고 컬럼 주석을 다는 이 프로젝트 관례에 더 맞지만, 항목 추가마다 마이그레이션이 필요하고 무엇보다 "`.env` 폴백"을 NULL로 표현해야 해서 의미가 흐려진다. 타입·범위 검증은 `RuntimeSettings`가 단일 지점에서 전담한다.

### 2-2. 쿼리 — `app/queries/system_settings.sql`

| 이름 | 용도 |
|---|---|
| `select_all_settings` | 전 행 조회 (`key`, `value`) |
| `upsert_setting` | `key` 충돌 시 `value`·`updated_at`·`updated_by` 갱신 |
| `delete_setting` | 기본값으로 되돌릴 때 행 삭제 |

항목이 늘어도 쿼리는 이 3개로 고정이다.

## 3. 런타임 설정 계층

### 3-1. `RuntimeSettings` — `app/runtime_settings.py`

Pydantic 모델 하나가 화이트리스트·타입·범위·기본값을 전부 맡는다. 필드에 없는 키는 DB에 있어도 무시한다 — 예전 설정이 남아 있어도 안전하다.

| 필드 | 타입 | 기본값 출처 (`.env`) |
|---|---|---|
| `script_provider` | `Literal["fake","openai","claude"]` | `SCRIPT_PROVIDER` (`openai`) |
| `voice_provider` | `Literal["fake","edge_tts"]` | `VOICE_PROVIDER` (`edge_tts`) |
| `captions_provider` | `Literal["fake","whisper"]` | `CAPTIONS_PROVIDER` (`whisper`) |
| `render_provider` | `Literal["fake","slideshow","stock"]` | `RENDER_PROVIDER` (`slideshow`) |
| `whisper_model` | `Literal["tiny","base","small","medium","large-v3"]` | `WHISPER_MODEL` (`small`) |
| `render_bg_color` | `str` (`#RRGGBB` 정규식) | `RENDER_BG_COLOR` (`#0f172a`) |
| `render_font` | `str` (1~100자) | `RENDER_FONT` (`Malgun Gothic`) |
| `render_font_size` | `int` (`ge=8, le=200`) | `RENDER_FONT_SIZE` (`30`) |
| `stock_sources` | `list[Literal["pexels","pixabay"]]` (중복 불가, 1개 이상) | `STOCK_SOURCES` |
| `stock_max_bytes` | `int` (`ge=1MB, le=500MB`) | `STOCK_MAX_BYTES` (50MB) |
| `stock_timeout_sec` | `int` (`ge=5, le=300`) | `STOCK_TIMEOUT_SEC` (`30`) |
| `failed_login_limit` | `int` (`ge=1, le=100`) | `FAILED_LOGIN_LIMIT` (`5`) |
| `password_min_len` | `int` (`ge=8, le=128`) | 신규 (기본 `8`) |
| `signup_auto_approve` | `bool` | 신규 (기본 `false`) |

provider 목록은 `app/providers/base.py`의 `REGISTRY`와 일치해야 한다. `Literal`을 손으로 적는 대신 `REGISTRY` 키에서 유도해, provider를 추가하면 설정 선택지가 자동으로 따라오게 한다.

`password_min_len`의 하한을 8로 못박는다. 설정으로 열되 지금 수준 아래로는 내릴 수 없다 — 관리자 실수로 보안이 후퇴하는 경로를 만들지 않는다.

`stock_max_bytes`는 DB·API에서 바이트로 다루고 화면에서만 MB로 환산한다. 단위 변환 지점을 한 곳으로 묶는다.

### 3-2. 조회와 캐시

```python
async def get_runtime_settings(conn) -> RuntimeSettings
def invalidate_runtime_settings() -> None
```

`select_all_settings`로 읽은 `{key: value}`를 `.env` 기본값 위에 덮어쓰고 `RuntimeSettings`로 파싱한다.

캐시는 **프로세스 내 TTL 30초 + 저장 시 즉시 무효화**를 함께 쓴다. 저장 무효화만 두면 다중 프로세스 배포에서 다른 프로세스에 변경이 영원히 닿지 않고, TTL만 두면 관리자가 저장 직후 화면에서 이전 값을 본다. 둘을 같이 두면 같은 프로세스는 즉시, 다른 프로세스는 최대 30초 안에 따라잡는다.

**`get_settings()`와 섞지 않는다.** `get_settings()`는 `@lru_cache`로 프로세스 생명주기 동안 고정이고 `DATABASE_URL`·`JWT_SECRET`처럼 부팅에 필요한 값을 담는다. `RuntimeSettings`가 그 위에 얹히는 별개 계층이고, 두 함수의 역할이 겹치지 않게 유지한다.

DB 조회가 실패하면 `.env` 기본값으로 조용히 폴백하고 경고를 남긴다. 설정 테이블 장애가 파이프라인 전체를 멈추게 하지 않는다.

### 3-3. provider에 설정을 전달하는 방법

`get_runtime_settings()`는 커넥션이 필요한데 provider는 커넥션이 없다. provider가 직접 DB를 읽게 하면 안 된다.

**파이프라인이 `StageContext.settings`에 실어 넘긴다.** `pipeline.run_stage`는 이미 `conn`을 쥐고 있고, `StageContext.settings`는 이미 존재하며, `provider.validate(ctx.settings)`가 이미 그 값을 받고 있다(`app/core/pipeline.py:125`). provider의 `get_settings()` 호출을 `ctx.settings` 조회로 바꾸면 기존 구조에 그대로 얹힌다.

부수 효과로 provider가 전역 설정에 대한 의존을 잃는다. 테스트에서 `ctx.settings`에 dict를 넣어주면 되므로 `get_settings()`를 몽키패치할 필요가 없어진다.

### 3-4. 호출부 교체

| 위치 | 현재 | 변경 후 |
|---|---|---|
| `app/api/projects.py:76` | `get_settings().script_provider` | `get_runtime_settings(conn)` |
| `app/core/pipeline.py:152` `_next_provider` | `getattr(get_settings(), ...)` | 런타임 설정에서 조회 (커넥션을 인자로 받도록 시그니처 변경) |
| `app/core/pipeline.py` `run_stage` | — | `ctx.settings`에 런타임 설정 주입 |
| `app/providers/render/slideshow.py:28` | `get_settings()` | `ctx.settings` |
| `app/providers/render/sources.py:24` | `get_settings()` | `ctx.settings` |
| `app/providers/render/stock.py:51,71` | `get_settings()` | `ctx.settings` |
| `app/providers/captions/whisper.py:57` | `get_settings().whisper_model` | `ctx.settings` |
| `app/auth/router.py:120` | `get_settings().failed_login_limit` | `get_runtime_settings(conn)` |
| `app/auth/router.py:241` | `_PASSWORD_MIN_LEN` 상수 | `get_runtime_settings(conn)` |
| `app/auth/router.py:45` `register` | 검증 없음 | 길이 검증 추가 + 자동 승인 분기 |

API 키(`openai_api_key` 등)는 `.env`에 남으므로 `ClaudeScript`·`OpenAIScript`의 `get_settings()` 호출은 그대로 둔다.

## 4. 가입 흐름 변경

현재 `register`는 무조건 `UserStatus.PENDING`으로 넣고(`app/auth/router.py:65`) 비밀번호 길이를 보지 않는다. `_PASSWORD_MIN_LEN = 8`은 비밀번호 **변경**에서만 쓰이고(`app/auth/router.py:221,241`), 프론트 `web/src/pages/Settings.tsx`에도 같은 상수 8이 따로 박혀 있다. 값이 세 곳에 흩어져 있고 그중 가입 경로에는 검증 자체가 없다.

**변경**

1. `register`에 비밀번호 길이 검증을 추가한다 — 미달이면 `WEAK_PASSWORD` 400. 비밀번호 변경과 같은 에러 코드·메시지를 쓴다.
2. `signup_auto_approve`가 참이면 `UserStatus.ACTIVE`로 넣는다. 거짓이면 지금처럼 `PENDING`.
3. `_PASSWORD_MIN_LEN` 상수를 지우고 두 경로 모두 런타임 설정을 읽는다.
4. 비인증 엔드포인트 `GET /auth/policy`를 추가해 프론트가 최소 길이를 서버에서 받게 한다(6절).

**기존 가입자에게 소급 적용하지 않는다.** 최소 길이를 올려도 기존 비밀번호는 그대로 쓸 수 있다. 강제 재설정은 이 작업의 범위가 아니다.

`signup_auto_approve`를 켜면 승인 대기 화면(`PendingApproval`)을 거치지 않고 바로 로그인된다. 이미 `PENDING`인 사용자는 자동으로 승인되지 않는다 — 설정은 이후 가입에만 적용되고, 대기 중인 사용자는 관리자가 `/admin/approvals`에서 처리한다.

## 5. API — `app/api/admin_system.py`

`prefix="/admin/system"`, `tags=["admin"]`. 두 엔드포인트 모두 `require_admin` 의존.

### `GET /admin/system/settings`

```json
{
  "settings": { "script_provider": "openai", "failed_login_limit": 5, ... },
  "defaults": { "script_provider": "openai", "failed_login_limit": 5, ... },
  "overridden": ["render_font_size"]
}
```

`settings`는 현재 유효값, `defaults`는 `.env` 기본값, `overridden`은 DB 행이 있는 키 목록이다. 화면이 "변경됨" 배지와 [기본값으로] 링크를 그리는 데 셋 다 필요하다.

### `PUT /admin/system/settings`

요청 본문은 `RuntimeSettings` 전체다. 공지 관리 모달이 항상 전체 필드를 보내는 관례와 맞춘다 — 부분 업데이트는 어떤 필드가 "안 보낸 것"인지 "비운 것"인지 구분해야 해서 화면과 서버 양쪽이 복잡해진다.

저장 로직:

- 값이 기본값과 다르면 `upsert_setting`
- 값이 기본값과 같으면 `delete_setting` (2-1절)
- 전부 한 트랜잭션. 커밋 후 `invalidate_runtime_settings()`
- 응답은 `GET`과 같은 형태 — 화면이 저장 직후 상태를 다시 조회하지 않아도 된다

범위·타입 위반은 FastAPI가 `RuntimeSettings` 파싱 단계에서 422로 거른다(공지 관리 API와 같은 방식). 그 밖의 실패는 프로젝트 전역 규약대로 `AppError` → `{code, message}`로 응답한다.

## 6. 화면 — `web/src/pages/admin/AdminSystem.tsx`

`Settings.tsx` 안에 사적으로 있는 `SettingRow`를 `web/src/components/SettingRow.tsx`로 승격해 두 화면이 공유한다. 개인 설정과 시스템 설정이 같은 줄 모양을 갖는 것이 맞고, 지금 옮기지 않으면 복사본이 생긴다.

**구성**

- 섹션 2개: `파이프라인 기본값`, `계정 · 보안`. `Settings.tsx`와 같은 카드 스타일
- 각 행 오른쪽에 입력 컨트롤 — 선택은 `<select>`, 색상은 색상 입력 + hex 텍스트, 숫자는 `<input type="number">`, 스톡 소스는 순서를 바꿀 수 있는 목록
- 기본값과 다른 행에는 "변경됨" 표시와 [기본값으로] 링크
- 하단 [저장]은 변경이 있을 때만 활성화. 저장 성공 시 상단 배너

**설명 문구를 형식적으로 채우지 않는다.** 각 행의 설명은 "이 값을 바꾸면 무엇이 달라지는가"를 적는다. 특히 provider 항목은 "새로 만드는 프로젝트부터 적용됩니다", 렌더·Whisper 항목은 "다음 실행부터 적용됩니다"라고 명시한다 — 적용 시점이 항목마다 다르다는 것이 이 화면에서 가장 혼동하기 쉬운 지점이다.

**비밀번호 최소 길이 공유.** `Settings.tsx`의 `PASSWORD_MIN_LEN = 8` 하드코딩을 없애고 서버 값을 쓴다.

이를 위해 비인증 엔드포인트 `GET /auth/policy` → `{"password_min_len": 8}`를 추가한다. 회원가입 화면이 로그인 전에 이 값을 필요로 하므로 `GET /auth/me`로는 전달할 수 없고(현재 프론트는 로그인 직후 `/auth/me`를 건너뛴다 — `web/src/lib/auth.tsx:36`), 일반 사용자에게 관리자 설정 API를 열 수도 없다. 최소 길이는 가입을 시도하면 어차피 드러나는 값이라 공개해도 잃을 것이 없다.

`Register.tsx`와 `Settings.tsx`가 이 값을 받아 입력 힌트와 클라이언트 검증에 쓴다. 서버 검증이 최종 권한이고 화면 검증은 즉각적인 피드백용이라는 기존 구조(`Settings.tsx`의 주석)를 그대로 유지한다.

## 7. 테스트

**런타임 설정 계층**

- DB가 비었을 때 `RuntimeSettings`의 모든 필드가 `.env` 값과 같다 (폴백)
- 행이 있으면 그 값이 `.env`를 이긴다
- `RuntimeSettings`에 없는 키가 DB에 있어도 무시된다
- 범위를 벗어난 값(`password_min_len=4`, `render_font_size=0`)은 파싱에서 거부된다
- DB 조회 실패 시 기본값으로 폴백하고 예외를 던지지 않는다
- `PUT` 직후 `GET`이 새 값을 준다 (캐시 무효화)
- 기본값과 같은 값을 저장하면 행이 삭제된다

**파이프라인**

- 설정을 바꾸면 새 프로젝트의 SCRIPT 단계 provider가 바뀐다
- 이미 만들어진 단계의 provider는 바뀌지 않는다 (스냅샷 유지)
- `ctx.settings`의 렌더 옵션이 ffmpeg 명령에 반영된다

**계정**

- 최소 길이 미달로 가입하면 400 `WEAK_PASSWORD`
- `signup_auto_approve`가 참이면 가입 결과가 `ACTIVE`, 거짓이면 `PENDING`
- 이미 `PENDING`인 사용자는 설정을 켜도 그대로 `PENDING`
- `failed_login_limit`을 바꾸면 잠금 시점이 그에 맞춰 바뀐다
- `GET /auth/policy`가 비인증으로 열리고, 설정을 바꾸면 응답의 `password_min_len`이 따라 바뀐다

**권한**

- 비관리자가 `GET`·`PUT` 모두 403

## 8. 마이그레이션

Alembic 리비전 하나: `system_settings` 테이블 생성. 시드 데이터 없음. 다운그레이드는 테이블 삭제.

기존 배포는 이 마이그레이션만 적용하면 테이블이 빈 채로 지금과 동일하게 동작한다. 롤백해도 `.env` 값이 그대로 살아 있으므로 서비스가 멈추지 않는다.
