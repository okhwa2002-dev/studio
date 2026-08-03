# 에러 로그 설계 (Design Spec)

- **작성일:** 2026-08-03
- **한 줄 요약:** 500 예외와 응답 밖에서 조용히 죽는 실패(워커·정리 잡·메일 발송)를 `error_logs` 테이블에 **지문 단위로 집계**한다. 관리자 화면은 이번 범위 밖이다.

---

## 1. 배경 & 목표

### 문제

지금 실패는 전부 `logger.exception`으로 `studio.log`에만 남는다. 그 파일은 자정마다 로테이션되고, 서버에 들어가 `grep`을 해야 볼 수 있으며, **무엇이 얼마나 자주 나는지** 알 방법이 없다. 특히 응답 밖에서 도는 실패는 아무도 모르게 지나간다:

- 워커의 단계 실행 실패 — 사용자는 "실행 중 오류" 문구만 본다.
- 정리 잡 실패 — 24시간 뒤 다시 시도할 뿐 아무 신호가 없다.
- **메일 발송 실패** — 계정 열거 방지 때문에 사용자에게도, 관리자에게도 알리지 않는다([이메일 발송 설계](2026-08-03-email-delivery-design.md) §2.6).

### 목표

이 실패들을 조회 가능한 형태로 DB에 남긴다. **"어떤 에러가, 어디서, 몇 번"** 이 한 눈에 보이는 것이 목적이다.

### 이번 범위

테이블 · 기록 함수 · 후킹 · 정리 잡. **백엔드만.**

### 비범위 (YAGNI)

- 관리자 화면(`/admin/errors`) — 에러가 실제로 어떻게 쌓이는지 본 뒤에 설계하는 편이 낫다.
- 슬랙·이메일 등 외부 알림.
- 4xx(`AppError`) 기록 — 비밀번호 오입력·404는 정상 동작이라 양만 많고 신호가 없다. 로그인 실패는 이미 `audit_logs`가 따로 기록한다.
- 스택트레이스 전문 저장 · 해결 표시(`resolved`) 플래그 · 담당자 지정.

---

## 2. 설계

### 2.1 테이블 `error_logs` — 지문당 한 행

| 컬럼 | 타입 | 설명 |
|------|------|------|
| `id` | BIGINT PK | `BaseEntity` |
| `fingerprint` | VARCHAR, **UNIQUE** | `source` + 예외 클래스 + 발생 위치. upsert 키 |
| `source` | VARCHAR, index | 어디서 났나 — `http`·`worker`·`pipeline`·`cleanup`·`email` |
| `exc_type` | VARCHAR | 예외 클래스명(`ValueError`) |
| `location` | VARCHAR | 앱 코드 기준 `디렉토리/파일:줄` |
| `message` | VARCHAR(200) | **마지막** 발생의 예외 메시지 |
| `context` | VARCHAR(200)? | **마지막** 발생의 부가 정보. 호출자가 명시적으로 넘긴 것만 |
| `count` | INTEGER | 누적 발생 횟수 (server_default 1) |
| 감사 컬럼 4개 | | `BaseEntity` 헬퍼 |

**`first_seen_at`·`last_seen_at`을 따로 두지 않는다.** `created_at`이 최초 발생이고 `updated_at`이 마지막 발생이다 — 이 테이블에서 행을 갱신하는 사건은 "또 발생했다" 하나뿐이라 두 쌍이 정확히 겹친다. 재설정 요청 이력 테이블에서 `requested_at`을 두지 않은 것과 같은 판단이다.

`message`와 `context`는 **마지막 발생 값으로 덮어쓴다.** 대표 예시 하나면 원인을 좁히는 데 충분하고, 전부 보존하면 지문으로 묶은 의미가 없어진다.

Alembic 리비전 1개로 추가하고 `docs/schema.sql`도 함께 갱신한다(기존 규칙).

### 2.2 지문 — 메시지를 넣지 않는다

```
fingerprint = f"{source}:{exc_type}@{location}"
```

**메시지를 넣지 않는 것이 핵심이다.** 예외 메시지에는 사용자 id·파일 경로·타임스탬프 같은 가변 값이 섞인다. 지문에 포함하면 같은 버그가 지문 수천 개로 흩어져, 집계로 얻으려던 "몇 번 났는가"가 전부 1이 된다.

`location`은 트레이스백에서 **가장 안쪽의 앱 코드 프레임**을 뽑아 `디렉토리/파일:줄` 형태로 만든다(예: `core/pipeline.py:136`). 라이브러리 내부 프레임이 아니라 우리 코드의 줄이어야 고칠 지점을 가리킨다. 앱 코드 프레임이 하나도 없으면(예: 미들웨어 밖에서 난 예외) 트레이스백의 마지막 프레임을 쓰고, 트레이스백 자체가 없으면 `unknown`으로 둔다 — 지문은 어떤 경우에도 만들어져야 한다.

`source`는 파이썬 상수로만 관리한다(`app/core/error_log.py`의 모듈 상수). `AuditAction`처럼 `app/constants.py`의 enum으로 올리지 않는 이유는, 이 값이 화면에 노출되지 않아 라벨 매핑 규칙(enum 독스트링이 요구하는 `AUDIT_ACTION_LABEL` 대응)을 따를 대상이 아니기 때문이다. 관리자 화면이 생기면 그때 올린다.

### 2.3 민감정보 — 담지 않는 것을 규칙으로 못박는다

이 설계에서 가장 조심할 곳이다. 기존 코드는 **인증코드를 로그에 절대 남기지 않는다**를 일관되게 지켜 왔다([비밀번호 재설정 설계](2026-07-31-password-reset-design.md) §2.3, 콘솔 출력을 의도적으로 넣지 않았다). 에러 기록이 그 구멍이 되면 안 된다.

- **스택트레이스 전문을 저장하지 않는다.** `파일:줄` 하나만 뽑는다.
- `message`는 200자로 자른다.
- `context`는 **호출자가 명시적으로 넘긴 문자열만** 담는다. 요청 본문·헤더·쿠키·쿼리스트링을 자동으로 긁지 않는다.
- **호출자 규칙: `context`에 비밀을 넣지 않는다.** 메일 발송 실패는 `to=a@example.com`까지만 — 인증코드·비밀번호·토큰은 넣지 않는다.

`message`가 예외 메시지 원문이라 이론상 값이 섞일 수 있다. 다만 이 앱에서 비밀을 다루는 경로(argon2 해시·SMTP 인증·JWT)는 예외 메시지에 원문을 싣지 않으므로, 200자 절단과 위 규칙으로 충분하다고 본다. 새 경로를 추가할 때 이 판단을 다시 확인한다.

### 2.4 기록 함수 — `app/core/error_log.py`

```python
async def record_error(source: str, exc: BaseException, context: str | None = None) -> None:
    """에러를 error_logs에 upsert한다. 어떤 경우에도 예외를 밖으로 내보내지 않는다."""
```

계약이 세 가지다.

**자기 세션을 연다** (`async_session_maker`). 두 가지 이유다:
- 백그라운드 태스크·워커·정리 잡에서 불린다. FastAPI 0.106부터 `yield` 의존성의 정리 코드가 백그라운드 태스크보다 **먼저** 돌기 때문에(이 프로젝트는 `fastapi>=0.115`), 요청 세션은 그 시점에 이미 닫혀 있다.
- 500 핸들러에서도 요청 세션은 방금 터진 예외로 트랜잭션이 깨져 있을 수 있어 쓸 수 없다.

**절대 던지지 않는다.** 에러를 기록하다 실패해서 원래 응답이 더 망가지면 본말전도다. 전체를 `try/except`로 감싸고 실패는 `logger.warning`으로만 남긴다.

**2초 타임아웃을 건다.** DB가 죽으면 모든 요청이 500이 나는데, 그때 기록 시도가 커넥션 타임아웃(수 초)만큼 매달리면 500 응답까지 함께 느려진다. 에러를 기록하려다 장애를 키우는 셈이다. `asyncio.wait_for(..., timeout=2)`로 상한을 두되, **세션 생성부터 커밋까지 전체를 감싼다** — 매달리는 지점이 대개 커넥션 획득이라 쿼리만 감싸면 소용이 없다. 타임아웃도 `except`가 삼키는 실패의 하나로 취급한다.

### 2.5 UPSERT

```sql
-- name: upsert_error_log<!
INSERT INTO error_logs
    (fingerprint, source, exc_type, location, message, context, count, created_at, updated_at)
VALUES
    (:fingerprint, :source, :exc_type, :location, :message, :context, 1, :now, :now)
ON CONFLICT (fingerprint) DO UPDATE SET
    count      = error_logs.count + 1,
    message    = EXCLUDED.message,
    context    = EXCLUDED.context,
    updated_at = EXCLUDED.updated_at
RETURNING id;
```

`updated_at`을 명시적으로 넣는다. `updated_at_field()`의 `onupdate`는 SQLAlchemy ORM 갱신에만 걸리고, 이 프로젝트의 aiosql 원시 쿼리에는 적용되지 않는다.

### 2.6 후킹 지점

기존 `logger.exception` 호출 옆에 `record_error`를 나란히 둔다.

| 위치 | source | context |
|---|---|---|
| [main.py:129](../../../app/main.py) `unhandled_exception_handler` | `http` | `POST /api/projects/3` |
| [worker.py:62](../../../app/core/worker.py) 단계 실행 중 처리되지 않은 예외 | `worker` | `stage=12` |
| [worker.py:123](../../../app/core/worker.py) 자동 진행 연쇄 실패 | `worker` | `stage=12` |
| [pipeline.py:136](../../../app/core/pipeline.py) 단계 실행 실패(외부 SDK 오류) | `pipeline` | `project=3 stage=voice` |
| [cleanup.py:167](../../../app/core/cleanup.py) 프로젝트 완전 삭제 실패 | `cleanup` | `project=7` |
| [cleanup.py:203](../../../app/core/cleanup.py) 정리 잡 실행 중 처리되지 않은 예외 | `cleanup` | 없음 |
| [password_reset.py](../../../app/auth/password_reset.py) 재설정 메일 발송 실패 | `email` | `to=a@example.com` |

**[events.py:32](../../../app/core/events.py)의 이벤트 발행 실패는 넣지 않는다.** `publish()`가 동기 함수라 `record_error`를 `await`할 수 없다. 이 한 곳 때문에 동기 진입점을 따로 만들 만한 가치가 없다 — SSE 구독자 큐 실패는 화면 갱신이 한 번 밀리는 수준이고, 워커·파이프라인 쪽이 같은 장애를 이미 잡는다.

**기존 `logger.exception`은 그대로 둔다.** 서버 로그는 스택트레이스 전문을 갖고 있어 원인을 파고들 때 여전히 필요하다. 테이블은 "무엇이 얼마나 자주 나는가"를 본다 — 역할이 겹치지 않는다.

### 2.7 정리 — 기존 잡에 단계 하나

```sql
-- name: delete_old_error_logs!
DELETE FROM error_logs WHERE updated_at < :before;
```

보관 기간은 소스 상수 `ERROR_RETENTION_DAYS = 30` (`AUDIT_RETENTION_DAYS = 90`과 같은 이유로 `.env`로 빼지 않는다 — 관리자가 바꿀 이유가 아직 없다).

**기준이 `updated_at`(마지막 발생)인 것이 핵심이다.** `created_at`으로 지우면 **오래전에 처음 났지만 지금도 나고 있는** 에러가 사라진다 — 가장 오래 방치된, 그래서 가장 봐야 할 항목이 먼저 지워지는 셈이다.

건수는 `_purge_old_audit_logs`처럼 서버 로그로 남긴다. 에러 로그는 행 수가 적어(지문 단위) 건수에 운영 신호가 있다.

---

## 3. 테스트

`tests/test_error_log.py`(신규)와 `tests/test_core_cleanup.py`에 나눠 넣는다.

| 테스트 | 검증 |
|--------|------|
| 첫 발생이 행을 만든다 | `count=1`, `source`·`exc_type`·`location`이 채워진다 |
| **같은 지문이 합쳐진다** | 같은 위치의 같은 예외 3번 → 행 1개, `count=3` |
| 마지막 값으로 덮어쓴다 | 두 번째 발생의 `message`·`context`가 남는다 |
| 다른 지문은 다른 행 | 예외 종류가 다르면 행이 나뉜다 |
| **메시지가 지문에 안 들어간다** | 같은 위치·같은 예외인데 메시지만 다르면 여전히 행 1개 |
| `message` 200자 절단 | 긴 예외 메시지가 잘려 저장된다 |
| **스택트레이스가 저장되지 않는다** | 어느 컬럼에도 여러 줄 트레이스백이 없다 |
| **기록 실패가 전파되지 않는다** | 쿼리가 터져도 `record_error`가 조용히 끝난다 |
| **DB가 죽어도 2초를 넘기지 않는다** | 세션 생성이 매달리면 타임아웃으로 끊긴다 |
| 500 응답이 기록을 남긴다 | 일부러 터지는 라우트 호출 → 행 1개, `source="http"` |
| **500 응답 본문이 그대로다** | 기록이 붙어도 `DEFAULT_ERROR` 응답이 바뀌지 않는다 |
| 정리 잡 — 오래된 것을 지운다 | `updated_at`이 보관 기간 밖인 행이 사라진다 |
| **정리 잡 — 최근 발생은 남긴다** | `created_at`은 오래됐지만 `updated_at`이 최근인 행은 남는다(§2.7) |

---

## 4. 다음 단계 (이번 범위 밖)

- **가입 승인/거절 이메일 알림** — 이 설계가 먼저인 이유다. 발송 실패를 `source="email"`로 여기에 남긴다.
- 관리자 화면(`/admin/errors`) — 실제로 무엇이 쌓이는지 본 뒤 목록·필터를 설계한다.
- `events.py`의 동기 경로 지원(2.6) — 필요해지면.
