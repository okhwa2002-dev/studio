# Studio

쇼츠 자동 생성 웹앱. (설계: docs/superpowers/specs/2026-07-09-studio-design.md)

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
| `npm run seed:sample` | 개발용 샘플 사용자 8명 (로컬 DB에서만 동작) |

Vite dev 서버가 `/auth`, `/admin/users`, `/health` 요청을 `http://localhost:8000`으로 프록시한다.
브라우저 입장에선 동일 출처이므로 CORS 설정 없이 httpOnly 인증 쿠키가 그대로 동작한다.

### 로그

앱 로그는 콘솔(stdout)과 파일(`LOG_DIR/studio.log`)에 같은 형식으로 남는다. 파일은 자정마다 로테이션된다.

```
2026-07-14 15:02:30 INFO app.sql - SQL 15.0ms INSERT INTO refresh_tokens (...) VALUES ($1, $2, ...) RETURNING id;
```

`.env`의 **`LOG_SQL=true`** 로 SQL 쿼리 로그를 켤 수 있다(기본값 `false`). 실행된 SQL과 소요시간만 남기고 **파라미터 값은 남기지 않는다** — 이 앱의 쿼리에는 `password_hash`와 리프레시 토큰 해시가 파라미터로 들어오기 때문이다.

### 동일 출처 규칙 (중요)

인증은 **httpOnly + SameSite=Lax 쿠키**에 의존한다. 이 방식은 프론트와 API가 **같은 출처**일 때만 성립한다.

- 개발: Vite 프록시가 동일 출처를 만든다.
- 운영: **FastAPI가 `web/dist`를 함께 서빙해야 한다.** (아직 구현 안 됨 — 배포 시 `StaticFiles` 마운트 + SPA 히스토리 폴백 필요)
- 프록시 접두사(`/auth`, `/admin/users`, `/health`) **아래에는 프론트 라우트를 만들지 않는다.** 주소창 입력·새로고침이 API로 넘어가 SPA 대신 JSON 404가 뜬다.

프론트를 별도 도메인/CDN에 올려야 한다면, **CORS를 켜기 전에 CSRF 방어부터 설계할 것.** 반사적으로 `CORSMiddleware` + `SameSite=None`을 켜면 이 설계의 XSS·CSRF 방어가 무너진다.

## 테스트

`npm test` (= `uv run pytest`). Docker 데몬이 떠 있어야 한다 — testcontainers가 임시 Postgres를 띄운다.
