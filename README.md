# Studio

쇼츠 자동 생성 웹앱. (설계: docs/superpowers/specs/2026-07-09-studio-design.md)

## 개발 실행

1. 의존성 설치: `uv sync`
2. 환경 파일: `cp .env.example .env` 후 값 확인 (DB 포트는 기본 5437)
3. DB 기동: `docker compose up -d db`
4. 마이그레이션: `uv run alembic upgrade head`
5. 최초 관리자 계정 생성(최초 1회): `uv run python scripts/seed_admin.py`
6. 서버 실행: `uv run uvicorn app.main:app --reload`
7. 확인: http://localhost:8000/health → `{"status":"ok"}`

## 프론트 실행

백엔드가 뜬 상태에서, 별도 터미널에서:

1. 의존성 설치(최초 1회): `cd web && npm install`
2. 개발 서버 실행: `npm run dev`
3. 접속: http://localhost:5173

Vite dev 서버가 `/auth`, `/admin`, `/health` 요청을 `http://localhost:8000`으로 프록시한다.
브라우저 입장에선 동일 출처이므로 CORS 설정 없이 httpOnly 인증 쿠키가 그대로 동작한다.

## 테스트

`uv run pytest` (Docker 데몬 실행 필요 — testcontainers가 임시 Postgres 기동)
