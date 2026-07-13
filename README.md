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
uv run alembic upgrade head              # 마이그레이션
uv run python scripts/seed_admin.py      # 최초 관리자 계정 (.env의 ADMIN_EMAIL/ADMIN_PASSWORD)
```

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

Vite dev 서버가 `/auth`, `/admin/users`, `/health` 요청을 `http://localhost:8000`으로 프록시한다.
브라우저 입장에선 동일 출처이므로 CORS 설정 없이 httpOnly 인증 쿠키가 그대로 동작한다.

### 동일 출처 규칙 (중요)

인증은 **httpOnly + SameSite=Lax 쿠키**에 의존한다. 이 방식은 프론트와 API가 **같은 출처**일 때만 성립한다.

- 개발: Vite 프록시가 동일 출처를 만든다.
- 운영: **FastAPI가 `web/dist`를 함께 서빙해야 한다.** (아직 구현 안 됨 — 배포 시 `StaticFiles` 마운트 + SPA 히스토리 폴백 필요)
- 프록시 접두사(`/auth`, `/admin/users`, `/health`) **아래에는 프론트 라우트를 만들지 않는다.** 주소창 입력·새로고침이 API로 넘어가 SPA 대신 JSON 404가 뜬다.

프론트를 별도 도메인/CDN에 올려야 한다면, **CORS를 켜기 전에 CSRF 방어부터 설계할 것.** 반사적으로 `CORSMiddleware` + `SameSite=None`을 켜면 이 설계의 XSS·CSRF 방어가 무너진다.

## 테스트

`npm test` (= `uv run pytest`). Docker 데몬이 떠 있어야 한다 — testcontainers가 임시 Postgres를 띄운다.
