# Studio — Plan 6: 관리자 시드 제거 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** `.env`의 `ADMIN_EMAIL`/`ADMIN_PASSWORD`와 관리자 시드 스크립트를 완전히 제거하고, 최초 관리자를 "회원가입 → SQL로 승격"으로 만들도록 문서를 바꾼다.

**Architecture:** 순수 제거 작업이다. 새 코드를 쓰지 않는다 — 설정 필드 2개, 모듈 2개, 테스트 파일 1개, npm 스크립트 1개, `.env` 항목 2개를 지우고, 그 자리를 문서(README + 상위 설계 문서)의 절차 안내로 대체한다.

**Tech Stack:** 기존 그대로 (Python 3.12, FastAPI, pydantic-settings, pytest).

**설계 문서:** `docs/superpowers/specs/2026-07-13-remove-admin-seed-design.md`

## Global Constraints

- **새 기능을 만들지 않는다.** 비밀번호 해시 생성 CLI, 관리자 승격 API, 관리자 생성 화면 — 전부 만들지 않는다. 최초 관리자는 회원가입 화면 + `UPDATE` 한 줄로 만든다.
- **`password_hash`는 argon2 해시다.** psql에서 평문으로 INSERT하면 계정은 생기지만 로그인 검증에 실패한다. 그래서 절차가 "가입(앱이 해시 생성) → 승격(UPDATE)" 순서인 것이다. 이 순서를 뒤집지 말 것.
- **샘플 시드(`app/auth/seed_sample_users.py`, `scripts/seed_sample_users.py`, `npm run seed:sample`)는 건드리지 않는다.** 관리자 시드와 별개 기능이다.
- **과거 Plan/Spec 문서(`docs/superpowers/plans/*`, 2026-07-13 이전 스펙)는 수정하지 않는다.** 그 시점의 결정을 기록한 히스토리다. 예외는 `docs/superpowers/specs/2026-07-09-studio-design.md` 하나 — 이것은 현재 시스템을 기술하는 살아있는 상위 설계 문서이므로 갱신한다.
- **기존 `admin@example.com` 계정은 DB에서 지우지 않는다.** 지우면 로그인할 관리자가 없어진다.
- 커밋은 각 Task 마지막 단계에서, 기존 스타일(한글, `변경:`/`정리:` 접두사)로 한다.

### 실행 환경 주의 (중요)

이 머신은 **Windows 애플리케이션 제어 정책이 `python.exe` 직접 실행을 차단**한다(`uv run ...` → `os error 4551`). **npm을 거치면 정상 실행된다.**

| 하려는 것 | 쓸 명령 |
|-----------|---------|
| 백엔드 테스트 | `npm test` |
| 백엔드 기동 | `npm run dev:api` |

pytest는 Docker 데몬이 떠 있어야 한다(testcontainers가 임시 Postgres를 띄운다).

---

## File Structure

```
studio/
├─ app/config.py                 # admin_email / admin_password 필드 삭제 (Task 1)
├─ app/auth/seed_admin.py        # 삭제 (Task 1)
├─ scripts/seed_admin.py         # 삭제 (Task 1)
├─ tests/test_seed_admin.py      # 삭제 (Task 1)
├─ package.json                  # seed:admin 스크립트 삭제 (Task 1)
├─ .env / .env.example           # ADMIN_EMAIL / ADMIN_PASSWORD 삭제 (Task 1)
├─ README.md                     # 시드 안내 → 승격 절차 (Task 2)
└─ docs/superpowers/specs/2026-07-09-studio-design.md   # 4장·7장 갱신 (Task 2)
```

---

## Task 1: 코드·설정에서 관리자 시드 제거

**Files:**
- Modify: `app/config.py`, `package.json`, `.env`, `.env.example`
- Delete: `app/auth/seed_admin.py`, `scripts/seed_admin.py`, `tests/test_seed_admin.py`

**Interfaces:**
- Produces: `app.config.Settings`에서 `admin_email`/`admin_password`가 사라진다. 이 두 필드를 읽던 코드는 모두 함께 삭제되므로 남는 참조가 없어야 한다.

- [ ] **Step 1: 시드 모듈과 테스트 삭제**

```bash
git rm app/auth/seed_admin.py scripts/seed_admin.py tests/test_seed_admin.py
```

- [ ] **Step 2: `app/config.py`에서 설정 필드 삭제**

`app/config.py`의 `Settings` 클래스에서 아래 두 줄을 지운다:

```python
    admin_email: str | None = None
    admin_password: str | None = None
```

다른 필드(`database_url`, `jwt_secret`, `app_timezone`, `storage_backend`, `storage_path`, `log_dir`, `cors_origins`, `secure_cookies`)는 그대로 둔다.

> `model_config`에 `extra="ignore"`가 걸려 있으므로, `.env`에 `ADMIN_EMAIL`이 남아 있어도 설정 로딩이 깨지지는 않는다. 그래도 `.env`에서 지운다(Step 4) — 쓰지 않는 값을 남겨두면 다음 사람이 "이건 뭐지" 하고 다시 조사한다.

- [ ] **Step 3: `package.json`에서 `seed:admin` 삭제**

`scripts`에서 아래 한 줄을 지운다. `seed:sample`을 포함한 나머지 스크립트는 그대로 둔다.

```json
    "seed:admin": "uv run python scripts/seed_admin.py",
```

- [ ] **Step 4: `.env`와 `.env.example`에서 항목 삭제**

두 파일 모두에서 아래 두 줄(과 그 위에 관련 주석이 있다면 함께)을 지운다:

```
ADMIN_EMAIL=...
ADMIN_PASSWORD=...
```

- [ ] **Step 5: 남은 참조가 없는지 확인**

Run: `grep -rniE "admin_email|admin_password|seed_admin|seed:admin|ensure_admin_seeded" app tests scripts package.json .env .env.example`
Expected: **출력 없음** (0건). 하나라도 남으면 지운다.

- [ ] **Step 6: 테스트 실행**

Run: `npm test`
Expected: PASS. 직전 상태는 80개였고, `tests/test_seed_admin.py`의 3개가 사라지므로 **77 passed**.

- [ ] **Step 7: 앱이 실제로 기동하는지 확인**

이 단계를 건너뛰지 말 것. `.env`에서 값을 지웠는데 `config.py`의 필드를 남겨두면(또는 그 반대) 설정 로딩 시점에 깨질 수 있고, **이 실패는 pytest로 잡히지 않는다**(테스트는 `DATABASE_URL`을 monkeypatch로 주입한다).

Run: `npm run dev:api`
Expected: `INFO:     Uvicorn running on http://127.0.0.1:8000` 이 뜬다. 에러 없이 기동하면 Ctrl+C로 종료한다.

- [ ] **Step 8: 커밋**

```bash
git add -A app/config.py package.json .env.example
git rm --cached -r --ignore-unmatch .env 2>/dev/null || true
git commit -m "정리: 관리자 시드 제거 (.env의 ADMIN_EMAIL/ADMIN_PASSWORD 및 seed_admin)"
```

> `.env`는 `.gitignore` 대상이므로 커밋에 포함되지 않는다. 로컬 파일만 수정하면 된다. `git rm --cached` 줄은 혹시 과거에 추적되고 있었을 경우를 대비한 안전장치이며, 추적 중이 아니면 아무 일도 하지 않는다.

---

## Task 2: 문서를 새 절차로 갱신

**Files:**
- Modify: `README.md`, `docs/superpowers/specs/2026-07-09-studio-design.md`

**Interfaces:**
- Consumes: Task 1이 지운 `npm run seed:admin`. 이 명령을 안내하는 문서가 남아 있으면 안 된다.

- [ ] **Step 1: README의 "최초 1회만" 블록 수정**

`README.md`의 최초 설정 블록에서 아래 두 줄 중 **`seed:admin` 줄만** 지운다 (`seed:sample` 줄은 남긴다):

```
npm run seed:admin                       # 최초 관리자 계정 (.env의 ADMIN_EMAIL/ADMIN_PASSWORD)
```

- [ ] **Step 2: README에 "최초 관리자 만들기" 절 추가**

`README.md`의 "### 매번 (개발 서버)" 절 **앞에** 아래 절을 넣는다:

````markdown
### 최초 관리자 만들기

가입은 자율이지만 로그인하려면 관리자 승인이 필요하다. 그런데 최초에는 승인해 줄 관리자가 없으므로, 첫 관리자만 DB에서 직접 승격시킨다.

1. 앱을 띄우고 `/register`에서 회원가입한다. (앱이 비밀번호를 argon2로 해시해 `PENDING` 상태로 저장한다)
2. 그 계정을 관리자로 승격시킨다:

   ```
   docker compose exec db psql -U studio -d studio -c "UPDATE users SET role='ADMIN', status='ACTIVE' WHERE email='내-이메일';"
   ```

3. 로그인한다. 이후 가입자는 이 관리자가 화면에서 승인한다.

> psql에서 계정을 직접 INSERT하지 말 것. `password_hash`는 argon2 해시라, 평문을 넣으면 계정은 생기지만 로그인 검증에 실패한다. 해시는 회원가입 화면이 만들어준다.
````

- [ ] **Step 3: README 명령 표에서 `seed:admin` 행 삭제**

명령 표에서 아래 행을 지운다. `seed:sample` 행은 남긴다.

```
| `npm run seed:admin` | 최초 관리자 계정 생성 |
```

- [ ] **Step 4: 상위 설계 문서 갱신 (4장)**

`docs/superpowers/specs/2026-07-09-studio-design.md`의 "가입·승인 흐름" 절에 있는 아래 줄을

```
- **최초 admin**은 시드 스크립트(`.env`의 `ADMIN_EMAIL/PASSWORD`, status=active, role=admin)로 생성.
```

아래로 교체한다:

```
- **최초 admin**은 회원가입 후 DB에서 승격시킨다(`UPDATE users SET role='ADMIN', status='ACTIVE' WHERE email=...`). 비밀번호 해시는 가입 화면이 만들어주므로 별도 시드 스크립트를 두지 않는다.
```

- [ ] **Step 5: 상위 설계 문서 갱신 (7장 설정 목록)**

같은 문서의 설정 목록에서 아래 줄을 **삭제**한다:

```
ADMIN_EMAIL / ADMIN_PASSWORD (최초 관리자 시드)
```

- [ ] **Step 6: 문서에 남은 참조 확인**

Run: `grep -rniE "seed:admin|ADMIN_EMAIL|ADMIN_PASSWORD" README.md docs/superpowers/specs/2026-07-09-studio-design.md`
Expected: **출력 없음** (0건).

> `docs/superpowers/plans/*`와 2026-07-13자 이전 스펙들에는 참조가 남아 있다. 그것들은 그 시점의 기록이므로 **고치지 않는다.**

- [ ] **Step 7: 문서에 적은 절차가 실제로 동작하는지 확인**

문서에 SQL을 적어놓고 실제로 통하는지 확인하지 않으면, 그 문서를 처음 따라 하는 사람이 디버거가 된다.

이미 시드된 샘플 계정으로 검증하고 원복한다. 백엔드를 띄운 상태에서:

```
docker compose exec db psql -U studio -d studio -c "UPDATE users SET role='ADMIN', status='ACTIVE' WHERE email='sample-member1@example.com';"
```

그 계정(`sample-member1@example.com` / `password123`)으로 로그인하면 응답이 `{"role":"ADMIN"}`이고, `GET /admin/users?status=PENDING`이 **200**을 반환해야 한다(승격 전에는 403이었다).

확인 후 원복한다:

```
docker compose exec db psql -U studio -d studio -c "UPDATE users SET role='MEMBER' WHERE email='sample-member1@example.com';"
```

- [ ] **Step 8: 커밋**

```bash
git add README.md docs/superpowers/specs/2026-07-09-studio-design.md docs/superpowers/specs/2026-07-13-remove-admin-seed-design.md docs/superpowers/plans/2026-07-13-plan6-remove-admin-seed.md
git commit -m "문서: 최초 관리자 생성을 가입 후 SQL 승격 방식으로 안내"
```

---

## 완료 조건

- `grep -rniE "admin_email|admin_password|seed_admin|seed:admin" app tests scripts package.json README.md .env .env.example` → 0건
- `npm test` → 77 passed
- `npm run dev:api` → 에러 없이 기동
- README에 적은 승격 SQL이 실제로 관리자 권한을 부여한다(Task 2 Step 7에서 확인)
