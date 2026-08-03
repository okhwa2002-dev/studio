# Studio

쇼츠 자동 생성 웹앱. (설계: docs/superpowers/specs/2026-07-09-studio-design.md)

## 기술 스택

### 백엔드 (`app/`)
| 항목 | 사용 기술 |
|------|-----------|
| 언어 | **Python 3.12+** |
| 웹 프레임워크 | FastAPI + Uvicorn(ASGI) |
| 스키마/모델 | SQLModel (SQLAlchemy 기반) |
| 데이터베이스 | PostgreSQL (드라이버: asyncpg) |
| 쿼리 | aiosql (`app/queries/*.sql` 이름 붙인 쿼리) |
| 마이그레이션 | Alembic |
| 설정 | pydantic-settings (`.env`) |
| 인증 | argon2-cffi(비밀번호 해시) · PyJWT(httpOnly 쿠키 JWT) |
| 대본 생성 | OpenAI · Anthropic SDK (교체 가능) |
| 음성(TTS) | edge-tts (무료, 키 불필요) |
| 자막(STT) | faster-whisper (로컬 CPU, torch 불필요) |
| 영상 합성 | imageio-ffmpeg (정적 ffmpeg 번들, H.264/AAC → 9:16 mp4) |
| 스톡 소재 | httpx + Pexels · Pixabay 무료 API |
| 테스트 | pytest · pytest-asyncio · httpx · testcontainers |
| 패키지 매니저 | uv |

### 프론트엔드 (`web/`)
| 항목 | 사용 기술 |
|------|-----------|
| 언어 | **TypeScript** |
| UI 프레임워크 | React 19 |
| 라우팅 | react-router-dom 7 |
| 빌드 도구 | Vite |
| 스타일 | Tailwind CSS 4 |
| 린트 | oxlint |
| 패키지 매니저 | npm |

### 인프라
- **PostgreSQL 하나로 통일** — 데이터 저장과 작업 큐(`stages` 테이블)를 모두 담당해 Redis가 필요 없다. 로컬은 `docker compose`로 기동.
- **단계 실행은 앱 내 백그라운드 워커**가 맡는다(`app/core/worker.py`). 별도 프로세스 없이 FastAPI `lifespan`에서 함께 뜨고, 상태·진행률은 SSE(`GET /api/projects/{id}/events`)로 UI에 푸시된다. 동시 실행 수는 `.env`의 `WORKER_CONCURRENCY`(기본 1)로 조절한다.

## 개발 실행

### 최초 1회만

```
uv sync                                  # 백엔드 의존성
cp .env.example .env                     # 환경 파일 (DB 포트는 기본 5437)
cd web && npm install                    # 프론트 의존성
```

```
docker compose up -d db                  # DB 기동
npm run migrate                          # 마이그레이션
npm run seed:sample                      # (선택) 개발용 샘플 사용자 8명 — 비밀번호는 모두 password123
```

> **captions 단계 최초 실행 시** whisper `small` 모델(~500MB)을 자동으로 내려받습니다.
> 그 첫 실행만 오래 걸리고 이후에는 캐시를 씁니다. 모델 크기는 `.env`의 `WHISPER_MODEL`로 바꿉니다
> (`tiny`|`base`|`small`|`medium`). 키 없이 쓰려면 `CAPTIONS_PROVIDER=fake`로 두세요.

### 최초 관리자 만들기

가입은 자율이지만 로그인하려면 관리자 승인이 필요하다. 그런데 최초에는 승인해 줄 관리자가 없으므로, 첫 관리자만 DB에서 직접 승격시킨다.

1. 앱을 띄우고 `/register`에서 회원가입한다. (앱이 비밀번호를 argon2로 해시해 `PENDING` 상태로 저장한다)
2. 그 계정을 관리자로 승격시킨다:

   ```
   docker compose exec db psql -U studio -d studio -c "UPDATE users SET role='ADMIN', status='ACTIVE' WHERE email='내-이메일';"
   ```

3. 로그인한다. 이후 가입자는 이 관리자가 화면에서 승인한다.

> psql에서 계정을 직접 INSERT하지 말 것. `password_hash`는 argon2 해시라, 평문을 넣으면 계정은 생기지만 로그인 검증에 실패한다. 해시는 회원가입 화면이 만들어준다.

### 매번 (개발 서버)

프로젝트 루트에서:

```
npm run dev
```

이 한 줄이 **DB(docker) → 백엔드(:8000) → 프론트(:5173)** 를 모두 띄운다.
로그는 `api` / `web` 접두사로 구분되고, **Ctrl+C 한 번에 둘 다 종료**된다.

접속: **http://localhost:5173** (`:8000`이 아니다 — API 요청은 Vite가 프록시로 넘긴다)

모든 명령은 루트에서 실행한다.

| 명령 | 하는 일 |
|------|---------|
| `npm run dev` | DB + 백엔드 + 프론트 전부 |
| `npm run dev:web` | 프론트만 |
| `npm run dev:api` | 백엔드만 |
| `npm test` | 백엔드 테스트 (pytest) |
| `npm run build` | 프론트 프로덕션 빌드 |
| `npm run lint` | 프론트 린트 (oxlint) |
| `npm run migrate` | 마이그레이션 적용 (alembic upgrade head) |
| `npm run migrate:down` | 마이그레이션 한 단계 되돌리기 |
| `npm run migrate:make -- "설명"` | 모델 변경으로부터 마이그레이션 생성 (autogenerate) |
| `npm run seed:sample` | 개발용 샘플 사용자 8명 (로컬 DB에서만 동작) |

Vite dev 서버가 `/auth`, `/admin/users`, `/health` 요청을 `http://localhost:8000`으로 프록시한다.
브라우저 입장에선 동일 출처이므로 CORS 설정 없이 httpOnly 인증 쿠키가 그대로 동작한다.

### 브랜치 · 커밋 · 머지

작업은 `main`에서 갈라진 브랜치에서 하고, 끝나면 `main`으로 되돌린다.

| 명령 | 하는 일 |
|------|---------|
| `git switch -c feat/기능이름 main` | `main`에서 작업 브랜치를 딴다 |
| `git add <파일...>` | 커밋할 파일을 고른다 (`git add .`은 쓰지 않는다 — 아래 참고) |
| `git commit` | 커밋한다 (메시지 규칙은 아래) |
| `npm test && npm run build && npm run lint` | **통합 전 검증** — 셋 다 통과해야 머지한다 |
| `git switch main && git pull` | 머지 대상을 최신으로 맞춘다 |
| `git merge --no-ff feat/기능이름` | 병합한다 (`--no-ff`로 기능 단위를 남긴다) |
| `npm test` | **병합 결과를 다시 검증한다** — 각자 통과해도 합치면 깨질 수 있다 |
| `git push origin main` | 원격에 올린다 |
| `git branch -d feat/기능이름` | 병합된 브랜치를 지운다 |

**커밋 메시지** — 한글로 쓰고 `feat:` / `fix:` / `test:` / `docs:` 접두사를 붙인다. 제목은 무엇을 했는지, 본문은 **왜 그렇게 했는지**를 적는다. 코드를 보면 아는 것(무엇이 바뀌었는지)은 본문에 옮겨 적지 않는다.

```
feat: 만료된 비밀번호 재설정 코드 정리 잡 추가

삭제 조건은 expires_at 하나다. refresh 토큰의 "폐기 행 보존" 규칙은 폐기
토큰 재사용을 탈취로 잡는 경보가 행의 존재에 의존해서인데, 재설정 코드에는
그 경보가 없다.
```

**커밋은 기능 단위로 나눈다.** 한 커밋이 하나를 한다 — 백엔드 API, 프론트 화면, 문서는 따로 커밋한다. 나누다 보면 파일 하나의 일부만 앞 커밋에 넣고 싶어질 때가 있는데, 그럴 땐 나중 커밋에 갈 부분을 잠시 지웠다가 되돌리는 편이 낫다. 쓰이지 않는 코드가 중간 커밋에 남지 않는다.

> `git add .`을 쓰지 않는 이유는 `.env`·`storage/`·`web/dist` 같은 것이 딸려 들어가서가 아니라(그건 `.gitignore`가 막는다), **무엇을 커밋하는지 보지 않게 되기 때문**이다. 파일을 이름으로 고르면 커밋 경계를 매번 다시 생각하게 된다.

> **병합 결과 검증을 건너뛰지 말 것.** 브랜치와 `main`이 각각 통과해도 합친 결과는 깨질 수 있다 — 양쪽이 같은 함수의 시그니처를 다르게 바꾼 경우가 흔하다. 병합 후 테스트가 깨지면 푸시하지 말고 그 자리에서 고친다(아직 로컬이라 되돌리기 쉽다).

> **푸시가 거절되면 force-push하지 말 것.** 거절은 원격이 움직였다는 뜻이다. `git pull`로 받아 합치고 다시 검증한다.

### 로그

앱 로그는 콘솔(stdout)과 파일(`LOG_DIR/studio.log`)에 같은 형식으로 남는다. 파일은 자정마다 로테이션된다.

```
2026-07-14 15:02:30 INFO app.sql - SQL 15.0ms INSERT INTO refresh_tokens (...) VALUES ($1, $2, ...) RETURNING id;
```

`.env`의 **`LOG_SQL=true`** 로 SQL 쿼리 로그를 켤 수 있다(기본값 `false`). 실행된 SQL과 소요시간만 남기고 **파라미터 값은 남기지 않는다** — 이 앱의 쿼리에는 `password_hash`와 리프레시 토큰 해시가 파라미터로 들어오기 때문이다.

### 활동 기록 (감사 로그)

`studio.log`와는 별개다. 위 파일이 개발자가 장애를 볼 때 읽는 것이라면, 활동 기록은 **누가 언제 무엇을 했는지**를 행위 단위로 남기는 DB 테이블(`audit_logs`)이다. 로그인·가입 승인·공지 수정·프로젝트 삭제 같은 사건이 여기 쌓인다.

관리자는 **`/admin/logs`** 화면에서 기간·행위·성공 여부·검색어로 조회한다. 기록은 **90일** 보관되고, 그보다 오래된 것은 정리 잡이 하루 한 번 지운다. 보관 기간은 `app/core/cleanup.py`의 소스 상수 `AUDIT_RETENTION_DAYS`이며 `.env`로 바꾸지 않는다.

> 이 기능은 `audit_logs` 테이블에 의존한다. 마이그레이션을 적용하지 않은 채 새 코드를 띄우면 **로그인부터 500**이 난다. 배포 시 `npm run migrate`를 먼저 돌릴 것.

### 에러 로그

`studio.log`가 스택트레이스 전문을 담아 "왜 터졌나"를 보는 것이라면, `error_logs` 테이블은 **"무엇이 얼마나 자주 터지나"** 를 본다. 로그 파일은 자정마다 로테이션되고 서버에 들어가야 볼 수 있어서, 특히 응답 밖에서 조용히 죽는 실패(워커·정리 잡·메일 발송)는 아무도 모르게 지나갔다.

기록되는 것은 **500 예외와 백그라운드 실패**뿐이다. 4xx(비밀번호 오입력·404 등)는 정상 동작이라 넣지 않는다 — 로그인 실패는 `audit_logs`가 따로 기록한다.

같은 에러는 **지문(`source` + 예외 클래스 + 발생 위치)으로 묶여 한 행에 `count`만 올라간다.** 지문에 예외 메시지를 넣지 않는 이유는, 메시지에 섞인 사용자 id 같은 가변 값 때문에 같은 버그가 지문 수천 개로 흩어지기 때문이다. DB가 끊겨 초당 수백 건이 나도 테이블은 커지지 않는다.

```sql
-- 최근에 많이 난 순서
SELECT source, exc_type, location, count, updated_at
FROM error_logs ORDER BY updated_at DESC LIMIT 20;
```

**민감정보는 담지 않는다.** 스택트레이스 전문을 저장하지 않고 `파일:줄` 하나만 뽑으며, 부가 정보(`context`)는 호출부가 명시적으로 넘긴 값만 들어간다 — 요청 본문·헤더·쿠키를 자동으로 긁지 않는다. 새 호출부를 추가할 때 **`context`에 인증코드·비밀번호·토큰을 넣지 말 것.**

기록은 30일 보관되고 정리 잡이 하루 한 번 지운다. 기준은 `updated_at`(마지막 발생)이라, 오래전에 처음 났지만 지금도 나는 에러는 지워지지 않는다. 보관 기간은 `app/core/cleanup.py`의 소스 상수 `ERROR_RETENTION_DAYS`다.

관리자 화면은 아직 없다 — 위 SQL로 조회한다.

### 비밀번호 재설정

로그인 화면의 **"비밀번호를 잊으셨나요?"** 로 여는 3단계 팝업이다(이메일 → 인증코드 확인 → 새 비밀번호). 6자리 코드는 `password_reset_codes` 테이블에 저장되고 10분 뒤 만료된다.

인증코드는 `.env`의 `SMTP_*` 설정으로 발송된다(`SMTP_HOST`·`SMTP_PORT`·`SMTP_USER`·`SMTP_PASSWORD`·`SMTP_FROM`·`SMTP_TLS`·`SMTP_TIMEOUT_SEC` — 값 설명은 `.env.example` 참고). 발송은 응답을 보낸 뒤 백그라운드로 이뤄진다 — 동기로 보내면 가입된 주소일 때만 응답이 느려져 계정 존재가 드러난다.

**`SMTP_HOST`가 비어 있으면 메일을 보내지 않고 `LOG_DIR/mail/*.eml` 파일로 저장한다.** 개발 중에는 이 파일을 열어 인증코드를 확인한다(Outlook·Thunderbird·VS Code에서 바로 열린다). 기동 시 로그에 이 상태가 경고로 남으므로, 운영에서 설정을 빠뜨렸는지 로그로 알 수 있다.

발송이 실패하면 사용자에게는 알리지 않고(계정 존재를 드러내지 않기 위해) 서버 로그에만 남는다. 이때는 테이블에서 코드를 직접 확인한다.

```sql
SELECT code FROM password_reset_codes
WHERE user_id = (SELECT id FROM users WHERE email = '...')
ORDER BY id DESC LIMIT 1;
```

만료된 코드는 정리 잡이 하루 한 번 지운다(`app/core/cleanup.py`). 보관 기간 설정은 없다 — 기준이 행 자신의 `expires_at`이다.

요청 빈도에는 상한이 있다(`app/auth/reset_rate_limit.py`). 실제 메일이 나가므로, 제한이 없으면 남의 주소로 요청을 반복해 그 사람 메일함을 채우거나 발신 계정의 하루 한도를 태워 정상 사용자까지 코드를 못 받게 만들 수 있다.

| `.env` 키 | 기본값 | 뜻 |
|---|---|---|
| `RESET_REQUEST_COOLDOWN_SEC` | 60 | 같은 이메일로 재요청할 수 있는 최소 간격(초). 0이면 끔 |
| `RESET_REQUEST_EMAIL_HOURLY` | 5 | 같은 이메일로 1시간에 허용할 요청 수 |
| `RESET_REQUEST_IP_HOURLY` | 20 | 같은 IP로 1시간에 허용할 요청 수 |

초과하면 `429 TOO_MANY_RESET_REQUESTS`를 통일된 문구로 돌려준다. **판정은 계정을 조회하기 전에** 하므로 429가 계정 존재를 알려주지 않고, **거부된 요청은 기록하지 않으므로** 공격이 이어져도 창이 밀리지 않는다(밀린다면 피해자가 영영 재설정하지 못한다). 어느 축에 걸렸는지는 서버 로그에만 남는다.

IP는 감사 로그와 같이 `request.client.host`만 본다 — 프록시 없는 단독 배포라 `X-Forwarded-For`를 신뢰하면 헤더 한 줄로 IP 축이 무력해진다. 프록시 뒤에 두는 배포로 바뀌면 이 결정을 다시 봐야 한다.

이 이력은 `password_reset_requests` 테이블에 쌓이고, 창(1시간)을 벗어난 행은 정리 잡이 지운다.

### 동일 출처 규칙 (중요)

인증은 **httpOnly + SameSite=Lax 쿠키**에 의존한다. 이 방식은 프론트와 API가 **같은 출처**일 때만 성립한다.

- 개발: Vite 프록시가 동일 출처를 만든다.
- 운영: **FastAPI가 `web/dist`를 함께 서빙한다.** (`app/main.py`의 `mount_spa` — `web/dist`가 있으면 `/assets`를 정적 마운트하고 나머지 경로는 `index.html`로 폴백한다. 빌드가 없으면 아무것도 하지 않아 개발에는 영향이 없다. 배포 전 `npm run build`로 `web/dist`를 만들어 둘 것.)
- 프록시 접두사(`/auth`, `/admin/users`, `/health`) **아래에는 프론트 라우트를 만들지 않는다.** 주소창 입력·새로고침이 API로 넘어가 SPA 대신 JSON 404가 뜬다.

프론트를 별도 도메인/CDN에 올려야 한다면, **CORS를 켜기 전에 CSRF 방어부터 설계할 것.** 반사적으로 `CORSMiddleware` + `SameSite=None`을 켜면 이 설계의 XSS·CSRF 방어가 무너진다.

> 앱이 뜰 때 이전 실행에서 `RUNNING`으로 남은 단계는 자동으로 실패 처리된다(중간 산출물 상태를 알 수 없기 때문). 상세 화면에서 다시 실행하면 된다.

## 테스트

`npm test` (= `uv run pytest`). Docker 데몬이 떠 있어야 한다 — testcontainers가 임시 Postgres를 띄운다.
