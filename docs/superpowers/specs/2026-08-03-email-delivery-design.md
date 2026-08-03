# 이메일 발송 설계 (Design Spec)

- **작성일:** 2026-08-03
- **한 줄 요약:** SMTP로 메일을 보내는 범용 발송기 `send_email()`을 만들고, 그 첫 사용처로 비밀번호 재설정 인증코드 메일을 붙인다. [비밀번호 재설정 설계](2026-07-31-password-reset-design.md) §0의 보안 경고를 해소하는 작업이다.

---

## 1. 배경 & 목표

### 문제

[비밀번호 재설정](2026-07-31-password-reset-design.md)은 6자리 인증코드를 `password_reset_codes`에 저장하지만, 그 코드를 사용자에게 전달하는 경로가 없다. 전달 경계로 `deliver_reset_code(email, code)` 함수를 하나 남겨 뒀고 몸통은 비어 있다. 그래서 지금은 **DB를 볼 수 있는 사람만** 비밀번호를 되찾을 수 있고, 자가 재설정 기능으로는 동작하지 않는다.

### 목표

`deliver_reset_code()`의 몸통을 실제 이메일 발송으로 채운다. 그 아래에 재사용 가능한 발송 계층을 하나 두어, 다음 메일(가입 승인 알림 등)이 생겼을 때 발송 계층을 다시 만들지 않게 한다.

### 이번 범위

- `app/core/email.py` — SMTP 발송기 1개 + 개발용 파일 폴백.
- `deliver_reset_code()` — 인증코드 메일의 제목·본문을 만들어 발송기에 넘긴다.
- 라우터가 발송을 **백그라운드로** 예약하도록 변경.
- `.env` 설정 7개, README 갱신, 테스트.

### 비범위 (YAGNI)

- 발송 이력 테이블 · 재시도 · 큐 — 실패하면 사용자가 다시 요청하면 된다(3.4).
- HTML 본문 · 템플릿 엔진 — 지금 메일은 한 종류다.
- 발송 rate limit · 반송(bounce) 처리 · 수신 거부.
- 관리자 화면에서의 SMTP 설정 — 비밀번호를 DB에 두지 않는다(2.2).

---

## 2. 설계

### 2.1 구조 — 3계층

```
router.py  ──BackgroundTasks──▶  deliver_reset_code(email, code)   [기존 함수, async로]
                                          │  제목·본문을 만든다
                                          ▼
                                 send_email(to, subject, body)      [app/core/email.py — 신규]
                                          │
                            ┌─────────────┴─────────────┐
                     SMTP_HOST 있음               SMTP_HOST 없음
                     aiosmtplib 발송              LOG_DIR/mail/*.eml 로 저장
```

경계가 지키는 것:

- `send_email()`은 **누가 왜 보내는지 모른다.** 받는 사람·제목·본문만 안다. 비밀번호 재설정을 import하지 않는다.
- `deliver_reset_code()`는 **어떻게 보내는지 모른다.** SMTP·파일 폴백·타임아웃을 모른다. 재설정 메일이 어떻게 생겼는지만 안다.

다음 메일(가입 승인 알림 등)을 붙일 때 건드릴 곳은 `send_email` **위층 하나**다. 발송 계층은 그대로 둔다.

`app/core/`에 두는 이유: `cleanup.py`·`worker.py`·`audit.py`와 같은 결의 "요청 처리 밖에서 도는 인프라"다. `app/utils/`는 순수 헬퍼(시간·경로·ffmpeg) 자리라 외부 접속을 하는 모듈은 맞지 않는다.

### 2.2 설정 — `.env` 전용 7개

`app/config.py`의 `Settings`에 추가한다.

| 키 | 기본값 | 설명 |
|---|---|---|
| `SMTP_HOST` | `""` | **비어 있으면 파일 폴백 모드.** 이 키 하나가 모드 스위치다 |
| `SMTP_PORT` | `587` | |
| `SMTP_USER` | `""` | 인증이 필요 없는 릴레이도 있으므로 빈 값 허용 |
| `SMTP_PASSWORD` | `""` | |
| `SMTP_FROM` | `""` | 발신자. 비면 `SMTP_USER`를 쓴다. `"Studio <no-reply@x.com>"` 형식도 그대로 허용 |
| `SMTP_TLS` | `"starttls"` | `starttls`(587) / `ssl`(465) / `none`(로컬 Mailpit 등) |
| `SMTP_TIMEOUT_SEC` | `15` | 백그라운드라도 무한정 매달리지 않게 한다 |

`.env.example`에도 같은 7개를 주석과 함께 추가한다.

**`runtime_settings`(관리자 화면)에는 넣지 않는다.** `system_settings` 테이블은 값을 JSON 문자열로 평문 저장하므로 SMTP 비밀번호가 DB에 그대로 앉는다. 기존 `openai_api_key`·`anthropic_api_key`·`pexels_api_key`가 모두 `.env` 전용인 것과 같은 선례다 — 비밀은 `.env`, 정책·취향은 관리자 화면.

**발신자 표시 이름을 위한 별도 키를 두지 않는다.** `SMTP_FROM`이 RFC 5322 주소 형식을 그대로 받으므로 `"Studio <no-reply@x.com>"`으로 충분하고, `SMTP_FROM_NAME`을 따로 두면 두 값을 조합하는 규칙이 생긴다.

**`SMTP_TLS`를 불리언 두 개(`use_tls`/`use_starttls`)로 쪼개지 않는다.** 셋 중 하나라는 사실이 값 하나에 드러나고, "둘 다 참"처럼 성립할 수 없는 조합이 표현되지 않는다.

### 2.3 개발 폴백 — `.eml` 파일

`SMTP_HOST`가 비어 있으면 메일을 보내는 대신 파일로 쓴다.

```
{LOG_DIR}/mail/20260803-142530-123_user_at_example.com.eml
```

- 파일명은 `{로컬시간 타임스탬프(ms)}_{수신자}.eml`. 수신자의 `@`는 `_at_`으로, 그 밖의 경로 금지 문자는 `_`로 치환한다. 밀리초까지 넣는 이유는 같은 초에 두 통이 나가도 덮어쓰지 않게 하기 위함이다.
- `log/`는 이미 `.gitignore` 대상이라 인증코드가 저장소에 섞이지 않는다.
- 디렉토리는 쓸 때 `mkdir(parents=True, exist_ok=True)`로 만든다.

**왜 콘솔·로그가 아닌 파일인가:** 재설정 설계가 콘솔 출력을 의도적으로 넣지 않았던 이유가 그대로 유효하다 — 서버 로그 파일에 인증코드 평문이 남고, 로그 수집기를 붙이면 그대로 외부로 나간다. `.eml`은 별도 파일이라 로그 파이프라인에 섞이지 않고, Outlook·Thunderbird·VS Code에서 바로 열려 본문·인코딩·제목을 눈으로 확인할 수 있다.

**왜 자동으로 폴백하는가(설정 없으면 실패시키지 않고):** 개발자가 SMTP 계정 없이도 재설정 플로우 전체를 끝까지 돌려볼 수 있어야 한다. 운영에서 `SMTP_HOST`를 빠뜨리면 메일이 조용히 파일로 가는 위험이 있는데, 이는 기동 로그에 남기는 것으로 다룬다(2.6).

### 2.4 메일 본문 — 플레인 텍스트

```
제목: [Studio] 비밀번호 재설정 인증코드

인증코드: 042917

이 코드는 10분 뒤에 만료됩니다.
본인이 요청하지 않았다면 이 메일을 무시하세요.
```

- 유효시간은 문자열로 박지 않고 기존 `RESET_CODE_TTL_MINUTES` 상수에서 가져온다. 상수를 바꾸면 메일 문구가 따라온다.
- 한글 제목·본문이므로 표준 라이브러리 `email.message.EmailMessage`에 맡긴다. `set_content(body)`가 UTF-8 인코딩을, 제목 헤더 대입이 RFC 2047 인코딩을 알아서 처리한다. 헤더를 손으로 조립하지 않는다.
- 본문에 링크·이름·계정 정보를 넣지 않는다. 코드가 잘못된 주소로 갔을 때 새어나갈 정보를 최소로 둔다.

### 2.5 라우터 변경 — 동기 호출을 백그라운드 예약으로

```python
async def password_reset_request(
    body: PasswordResetRequest,
    background: BackgroundTasks,              # 추가
    db: AsyncSession = Depends(get_db),
):
    ...
        await db.commit()
        # 커밋 이후에 예약한다 — 저장이 롤백됐는데 코드만 나가는 일이 없도록.
        background.add_task(deliver_reset_code, email, code)
```

**왜 백그라운드인가 — 계정 열거 방지가 걸려 있다.** 재설정 설계 §2.2는 계정 존재 여부를 숨기려고 응답 본문을 통일했다. 그런데 SMTP 발송을 응답 직전에 동기로 하면 **가입된 이메일일 때만 응답이 수 초 느려진다.** 본문이 같아도 응답 시간이 계정 존재를 알려주므로, 통일 응답이 무력해진다. `BackgroundTasks`는 응답을 보낸 **뒤** 태스크를 실행하므로 발송 시간이 응답에 섞이지 않는다.

`add_task`가 계정이 있을 때만 호출되는 것은 문제가 되지 않는다 — 등록 자체는 즉시 끝나고, 실행은 응답 이후다.

`BackgroundTasks`는 async 함수를 그대로 받으므로 `deliver_reset_code`를 `async def`로 바꾸면 된다. 이 프로젝트에는 아직 `BackgroundTasks` 사용처가 없다(백그라운드 작업은 `cleanup.py`·`worker.py`가 `asyncio.create_task`로 도는 상주 루프뿐이다). 여기서는 요청당 1회성 작업이라 FastAPI가 생애주기를 관리하는 `BackgroundTasks`가 맞다 — 맨 `create_task`는 참조를 잡아두지 않으면 GC로 사라질 수 있고 앱 종료 시 대기 보장도 없다.

### 2.6 실패 처리 — 삼키고 로그만

```python
try:
    await send_email(to=email, subject=..., body=...)
except Exception:
    logger.warning("이메일 발송 실패: to=%s subject=%s", to, subject, exc_info=True)
```

- **사용자에게 전파하지 않는다.** 백그라운드라 응답은 이미 나갔다. 설령 전파할 수 있어도 "이 주소로는 발송이 실패했다"는 응답 자체가 계정 존재를 알려준다.
- **로그에 코드·본문을 남기지 않는다.** 수신자·제목·예외만 남긴다. (수신자는 이미 요청자가 입력한 값이므로 새로 새는 정보가 없다.)
- **재시도하지 않는다.** 사용자가 다시 요청하면 새 코드가 발급되고 이전 코드는 무효화된다(재설정 설계 §2.2). 실패한 코드도 10분 뒤 만료되고 정리 잡이 지운다. 재시도 큐가 감당할 실패 모드가 없다.
- `BackgroundTasks`에서 예외가 새어나가면 서버 로그에 트레이스백이 찍히지만 응답에는 영향이 없다. 그래도 여기서 잡는 이유는 **로그 형태를 우리가 정하기 위해서**다 — 원문 예외가 그대로 찍히면 SMTP 라이브러리가 본문을 포함해 덤프할 여지가 있다.

**기동 시 안내 한 줄:** `app/main.py`의 lifespan에서 `SMTP_HOST`가 비어 있으면 `logger.warning("SMTP_HOST가 없어 메일을 파일로 저장합니다: {LOG_DIR}/mail")`을 남긴다. 운영에서 설정을 빠뜨리면 메일이 조용히 파일로 가는데, 이 한 줄이 그 상태를 기동 로그에 드러낸다. 기동을 막지는 않는다 — 개발 환경이 정상 경로이기 때문이다.

### 2.7 의존성

`pyproject.toml`에 `aiosmtplib>=3.0` 추가.

표준 라이브러리 `smtplib`는 블로킹이라 이벤트 루프를 멈춘다. `BackgroundTasks`의 async 함수 안에서 부르면 그 사이 다른 요청이 처리되지 않는다. `aiosmtplib`는 같은 `EmailMessage` 객체를 그대로 받으므로 본문 조립은 표준 라이브러리 그대로 쓴다.

---

## 3. 테스트

`tests/test_email.py`(신규)와 기존 `tests/test_password_reset_request.py`에 나눠 넣는다. `.eml` 출력 경로는 `tmp_path`로 `LOG_DIR`을 덮어써 테스트끼리 섞이지 않게 한다.

### 발송기 (`app/core/email.py`)

| 테스트 | 검증 |
|---|---|
| SMTP 미설정 → 파일 저장 | `.eml` 1개 생성, 수신자·제목·본문이 담긴다 |
| 파일명 충돌 없음 | 같은 수신자에게 연속 2통 → 파일 2개 |
| SMTP 설정 → aiosmtplib 호출 | `aiosmtplib.send`를 monkeypatch, 호스트·포트·발신자·TLS 모드 인자 확인 |
| `SMTP_FROM` 폴백 | 비어 있으면 `SMTP_USER`가 발신자가 된다 |
| 한글 인코딩 | 저장된 `.eml`을 `email.parser`로 다시 읽어 제목·본문이 원문과 같다 |

### 재설정 메일 (`deliver_reset_code`)

| 테스트 | 검증 |
|---|---|
| 본문에 코드가 들어간다 | 6자리 코드 문자열이 본문에 그대로(앞자리 0 포함) |
| 유효시간이 상수를 따른다 | 본문의 분 표기가 `RESET_CODE_TTL_MINUTES`와 일치 |
| 발송 실패가 새지 않는다 | `send_email`이 예외를 던져도 `deliver_reset_code`가 조용히 끝난다 |

### 엔드포인트

| 테스트 | 검증 |
|---|---|
| 요청이 발송을 예약한다 | 실재 이메일로 요청 → `.eml` 1개. 기존 `conftest.py`의 `AsyncClient` + `ASGITransport`는 ASGI 호출이 끝날 때까지 기다리고 백그라운드 태스크는 그 안에서 실행되므로, `await client.post(...)`가 돌아온 시점에 파일이 이미 있다 |
| 미존재 이메일은 발송 없음 | `.eml` 0개 — 기존 "저장 0건" 테스트와 짝을 이룬다 |
| 비활성 계정은 발송 없음 | `DISABLED`/`REJECTED`로 요청 → `.eml` 0개 |
| 응답에 코드 없음 | 기존 테스트 유지 |

---

## 4. 문서 갱신

### README

`### 비밀번호 재설정` 절의 **⚠️ 경고 블록을 삭제한다.** 그 경고의 해소가 이 작업의 목적이다. 자리에 SMTP 설정 안내를 넣는다.

- `.env`에 `SMTP_*`를 넣으면 인증코드가 실제로 발송된다는 한 줄 + 키 목록.
- `SMTP_HOST`가 없으면 `LOG_DIR/mail/*.eml`로 저장된다는 개발 안내. 기존의 "테이블에서 코드 확인" SQL은 **남긴다** — 발송이 실패했을 때 코드를 확인하는 마지막 수단이라 여전히 유효하다.

### 기존 설계 문서

[2026-07-31 비밀번호 재설정 설계](2026-07-31-password-reset-design.md) §0 보안 경고 상단에 **"해소됨 (2026-08-03) — 이 문서로 대체"** 한 줄과 이 문서 링크를 추가한다. 본문은 히스토리이므로 지우지 않는다. 그대로 두면 강한 경고문이 이미 해결된 문제를 계속 경고하게 된다.

---

## 5. 다음 단계 (이번 범위 밖)

- 재설정 요청 rate limit — 한 주소로 메일을 반복 발송시키는 것을 막는다. 두 설계 문서가 모두 남겨 둔 항목이다.
- 가입 승인·거부 알림 메일 — `send_email()` 위에 함수 하나를 더하면 된다.
