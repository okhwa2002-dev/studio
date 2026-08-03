# 재설정 요청 rate limit 설계 (Design Spec)

- **작성일:** 2026-08-03
- **한 줄 요약:** 비밀번호 재설정 요청을 이메일별·IP별로 제한한다. 새 테이블 `password_reset_requests`가 원장이고, 판정은 계정을 조회하기 **전에** 한다.

---

## 1. 배경 & 목표

### 문제

[이메일 발송](2026-08-03-email-delivery-design.md)이 붙으면서 재설정 요청의 성격이 바뀌었다. 그 전에는 요청을 무한 반복해도 `password_reset_codes`에 행만 쌓여 무해했지만, 지금은 요청 한 번이 **실제 메일 한 통**이다. 남의 이메일 주소로 요청을 반복하면:

- 피해자 메일함에 인증코드 메일이 무한정 꽂힌다 — 우리 서버가 메일 폭탄의 가해자가 된다.
- 발신 계정의 하루 한도(Gmail 개인 계정 기준 약 500통)를 태우면 **정상 사용자도 코드를 받지 못한다.**
- 새 요청이 이전 코드를 무효화하므로([재설정 설계](2026-07-31-password-reset-design.md) §2.2), 피해자가 코드를 입력하려는 순간마다 그 코드가 죽는다 — 재설정 자체가 봉쇄된다.

기존 5회 시도 제한은 **코드 추측**만 막는다. **요청 횟수**를 막는 것은 아무것도 없다.

### 목표

요청 빈도에 상한을 씌워 위 셋을 모두 막되, [재설정 설계](2026-07-31-password-reset-design.md) §2.2가 세운 **계정 열거 방지를 깨지 않는다.**

### 비범위 (YAGNI)

- `Retry-After` 헤더 · 남은 시간 표시 — 한도 창을 정확히 알려주면 그 직전까지 최대로 긁어낼 수 있다.
- 관리자 화면에서의 한도 조절 — 잘못 만지면 서비스가 막히는 값이라 배포 시점 결정에 가깝다.
- IP 화이트리스트 · 다른 엔드포인트(로그인·가입)로의 확대.
- 분산 환경 대응 — 이 앱은 단일 프로세스다(2.7).

---

## 2. 설계

### 2.1 저장 — 새 테이블 `password_reset_requests`

| 컬럼 | 타입 | 설명 |
|------|------|------|
| `id` | BIGINT PK | `BaseEntity` |
| `email` | VARCHAR, index | **정규화된**(`strip().lower()`) 제출 이메일. 계정 존재와 무관하게 기록 |
| `client_ip` | VARCHAR?, index | `request.client.host`. 알 수 없으면 NULL |
| 감사 컬럼 4개 | | `BaseEntity` 헬퍼 (`created_at`·`created_by`·`updated_at`·`updated_by`) |

**`requested_at` 같은 컬럼을 따로 두지 않는다.** `created_at_field()`가 이미 그 시각이다. 하나 더 두면 같은 뜻의 컬럼이 둘이 되고, 어느 쪽이 진짜인지 매번 확인해야 한다.

**이메일은 반드시 정규화 후 저장한다.** 안 그러면 `a@x.com`과 `A@X.com`이 다른 버킷이 되어, 대소문자만 바꿔가며 제한을 무한히 우회할 수 있다. 라우터가 이미 `strip().lower()`로 정규화하므로 그 값을 그대로 넘긴다.

Alembic 리비전 1개로 추가하고 `docs/schema.sql`도 함께 갱신한다(기존 규칙).

### 2.2 판정 — `app/auth/reset_rate_limit.py` (신규)

```python
async def check_and_record(conn, email: str, client_ip: str | None, now) -> None:
    """한도를 넘으면 429를 던지고, 아니면 이번 요청을 기록한다."""
```

세 축을 **쿼리 한 번**으로 본다.

```sql
-- name: count_recent_reset_requests^
SELECT
    COUNT(*) FILTER (WHERE email = :email AND created_at > :cooldown_since) AS email_cooldown,
    COUNT(*) FILTER (WHERE email = :email AND created_at > :window_since)   AS email_window,
    COUNT(*) FILTER (WHERE client_ip = :client_ip AND created_at > :window_since) AS ip_window
FROM password_reset_requests
WHERE created_at > :window_since;
```

- `cooldown_since`(60초 전)는 `window_since`(1시간 전)와 같거나 그보다 뒤이므로(쿨다운 허용 상한이 3600초라 최악의 경우 같아진다), 바깥 `WHERE`가 세 필터를 모두 덮는다.
- **`client_ip`가 NULL이면 IP 축이 자연히 꺼진다.** SQL에서 `client_ip = NULL`은 어떤 행과도 매치되지 않아 카운트가 0이 된다 — 식별할 수 없는 것을 제한하지 않는다는 뜻이고, 이를 위해 파이썬 분기를 따로 두지 않는다.

판정은 **셋 다 `>=`** 다. 경계를 명시하면 다음과 같다(기본값 기준):

| 축 | 거부 조건 | 뜻 |
|---|---|---|
| 쿨다운 | `email_cooldown >= 1` | 60초 안에 이미 한 건이라도 있으면 거부 |
| 이메일 | `email_window >= 5` | 1시간 안에 5건이 쌓였으면 **6번째**를 거부 |
| IP | `ip_window >= 20` | 1시간 안에 20건이 쌓였으면 **21번째**를 거부 |

즉 설정값은 "1시간에 허용하는 최대 통과 횟수"다.

셋 중 하나라도 걸리면 던진다:

```python
AppError(429, "TOO_MANY_RESET_REQUESTS", "요청이 너무 잦습니다. 잠시 후 다시 시도해 주세요.")
```

세 축 중 어느 것에 걸렸는지 **응답으로 구분하지 않는다.** 구분해 주면 공격자가 어느 축을 우회해야 하는지 알게 된다.

### 2.3 거부된 요청은 기록하지 않는다

한도에 걸린 요청까지 기록하면, 공격자가 계속 때리는 동안 창이 끝없이 밀려 **피해자가 영원히 재설정을 못 하게 된다.** 보호 장치가 그대로 공격 도구가 된다.

통과한 요청만 기록하면 창이 정상적으로 흘러가, 공격이 멎은 뒤 쿨다운(60초)만 지나면 정상 사용자가 다시 시도할 수 있다. `check_and_record`가 판정을 통과한 경우에만 INSERT를 실행하는 이유다.

INSERT는 `created_at`을 **인자로 받은 `now`로 명시해서** 넣는다(`insert_reset_code`와 같은 방식). 서버 기본값(`server_default`)에 맡기지 않는 이유는 두 가지다 — 판정에 쓴 시각과 기록되는 시각이 같아야 하고, 테스트가 과거 요청을 만들 때 같은 쿼리를 쓸 수 있어야 한다.

### 2.4 라우터 통합 — 계정 조회 **앞**에서

```python
async def password_reset_request(
    body: PasswordResetRequest,
    background: BackgroundTasks,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    email = body.email.strip().lower()
    conn = await raw_connection(db)
    await check_and_record(conn, email, request.client.host if request.client else None, now_local())
    await db.commit()          # 기록을 즉시 커밋한다
    row = await queries.find_by_email(conn, email=email)
    ...  # 이하 기존 그대로
```

**순서가 곧 보안이다.** 계정을 조회하기 전에 판정하므로, 429를 받았다는 사실이 계정 존재를 알려주지 않는다. 만약 "발송이 일어날 때만" 제한을 걸면 `429 = 계정 있음`이 되어, 응답 본문을 통일해 지켜 온 계정 열거 방지가 rate limit 때문에 깨진다.

**여기서 커밋하는 이유:** 현재 코드는 계정이 있을 때만 커밋한다(`if row is not None` 블록 안). 미존재 이메일 경로에는 커밋이 없어서, 기록이 세션 종료와 함께 롤백되고 제한이 무력해진다.

### 2.5 IP는 `request.client.host`만 쓴다

[app/core/audit.py](../../../app/core/audit.py)가 감사 로그에서 세운 방침을 그대로 따른다 — 이 앱은 FastAPI가 `web/dist`를 직접 서빙하는 단독 배포라 프록시가 없고, 프록시가 없는데 `X-Forwarded-For`를 신뢰하면 누구나 헤더 한 줄로 IP를 위조할 수 있다.

**rate limit에서는 이 규칙이 감사 로그보다 더 중요하다.** 감사 로그의 IP 위조는 기록이 더러워지는 문제지만, rate limit의 IP 위조는 **제한 자체가 무력화되는** 문제다. 헤더 값만 매 요청 바꾸면 IP 축이 존재하지 않는 것과 같아진다.

프록시 뒤에 두는 배포로 바뀐다면 이 결정을 다시 봐야 한다 — 그때는 모든 요청의 IP가 프록시 하나로 보여 IP 축이 반대로 과하게 걸린다.

### 2.6 설정 — `.env` 전용 3개

| 키 | 기본값 | 허용 범위 | 막는 것 |
|---|---|---|---|
| `RESET_REQUEST_COOLDOWN_SEC` | `60` | 0~3600 | 연타 |
| `RESET_REQUEST_EMAIL_HOURLY` | `5` | 1~100 | 특정 피해자 메일 폭탄 |
| `RESET_REQUEST_IP_HOURLY` | `20` | 1~1000 | 발신 계정 하루 한도 소진 |

이 값이면 한 주소로 하루 최대 120통, 한 IP로 하루 최대 480통이다. 정상 사용자가 오타로 몇 번 재시도해도 걸리지 않는다.

창(1시간)은 키로 빼지 않는다 — 키 이름에 이미 들어 있고, 넷째 키를 만들 만큼 조절할 이유가 없다.

SMTP 설정과 같이 `runtime_settings`(관리자 화면)에는 올리지 않는다. `FAILED_LOGIN_LIMIT`과 성격이 비슷해 보이지만, 이건 잘못 내리면 서비스가 막히는 값이라 배포 시점 결정에 가깝다.

### 2.7 경합은 감수한다

동시 요청 둘이 나란히 검사를 통과해 기록이 2건 들어갈 수 있다. 잠금(`SELECT ... FOR UPDATE`·advisory lock)을 걸지 않는다 — 5회/시간 한도에서 가끔 6회가 되는 정도이고, 그 대가로 모든 재설정 요청이 직렬화된다.

이 앱은 단일 프로세스다([app/core/events.py](../../../app/core/events.py)의 SSE 이벤트 버스가 모듈 전역 인메모리 dict라 다중 프로세스 배포가 애초에 성립하지 않는다). 경합 창은 같은 이벤트 루프 안의 두 요청 사이로 좁다.

### 2.8 정리 — 기존 잡에 단계 하나

```sql
-- name: delete_old_reset_requests!
DELETE FROM password_reset_requests WHERE created_at < :cutoff;
```

`cutoff`는 `now - 1시간`(가장 긴 rate limit 창). `_purge_expired_reset_codes` 바로 뒤, 자기 세션으로 부른다.

**보관 기간 상수를 새로 두지 않는다.** 기준이 rate limit 창 그 자체라 정책 판단이 없다 — 재설정 코드 정리 설계 §2.5와 같은 방침이다.

잡은 24시간 주기라 그 사이에는 최대 24시간치 행이 쌓인다. `created_at` 인덱스를 두는 이유가 이것이다 — 공격이 진행 중일 때도 판정 쿼리가 느려지지 않아야 한다. 지워지지 않은 오래된 행이 판정을 바꾸지는 않는다(쿼리가 `created_at > :window_since`로 거른다). 테이블 크기 문제일 뿐이다.

### 2.9 감사 로그는 남기지 않는다

429는 서버 로그에 `warning`으로만 남긴다(수신 이메일·IP·어느 축인지). 감사 로그에 넣으면 무차별 공격 시 로그가 넘치는데, 그건 재설정 설계 §2.4가 요청·실패를 기록하지 않기로 한 이유와 정확히 같다. 감사 로그 정리 잡이 자기참조를 피한 것과도 같은 결이다.

---

## 3. 프론트 — 변경 없음

[web/src/lib/api.ts](../../../web/src/lib/api.ts)의 `toApiError`가 상태 코드와 무관하게 응답 본문의 `{code, message}`를 꺼내 `ApiError`로 던지고, [web/src/components/PasswordResetModal.tsx](../../../web/src/components/PasswordResetModal.tsx)의 1단계 폼에 이미 `<FormError message={error} />`와 `catch (e) { setError(e instanceof ApiError ? e.message : ...) }`가 있다.

429 메시지가 그대로 표시되므로 프론트 코드는 한 줄도 바꾸지 않는다. `npm run build`로만 확인한다.

---

## 4. 테스트

`tests/test_password_reset_rate_limit.py`(신규)에 넣는다. 시각을 넘겨 판정하므로(`check_and_record(..., now)`) 과거 요청은 `created_at`을 직접 조작해 만든다 — `time.sleep`으로 기다리지 않는다.

| 테스트 | 검증 |
|--------|------|
| 쿨다운 | 연속 2회 → 두 번째 429 |
| 쿨다운 경과 | 이전 요청을 61초 전으로 밀면 통과 |
| 이메일 시간당 한도 | 5회 후 6번째 429 |
| IP 시간당 한도 | 서로 다른 이메일 20개 후 21번째 429 |
| **미존재 이메일도 센다** | 가입 안 한 주소로 반복해도 429 — 계정 열거 방지의 핵심 |
| **429가 계정 존재를 흘리지 않는다** | 존재·미존재 이메일이 같은 횟수에서 같은 코드·메시지 |
| **거부된 요청은 기록되지 않는다** | 한도 도달 후 계속 때려도, 창이 지나면 즉시 통과(창이 밀리지 않음) |
| **`X-Forwarded-For`를 무시한다** | 헤더를 매번 바꿔도 같은 IP로 집계되어 IP 한도에 걸린다 |
| 대소문자 | `A@X.com`과 `a@x.com`이 같은 버킷 |
| 한도 내에서는 메일이 나간다 | 기존 `.eml` 테스트가 그대로 통과 |
| 정리 잡 | 창보다 오래된 행이 지워지고, 창 안의 행은 남는다 |

---

## 5. 다음 단계 (이번 범위 밖)

- 로그인·가입 엔드포인트로의 확대 — 같은 모듈을 재사용할 수 있게 만들되, 지금 당장의 필요는 재설정뿐이다.
- 프록시 뒤 배포로 바뀔 경우의 IP 취득 방식 재검토(2.5).
