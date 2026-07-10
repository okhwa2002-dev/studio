# Studio — 쇼츠 자동 생성 웹앱 설계 문서 (Design Spec)

- **작성일:** 2026-07-09
- **프로젝트명:** studio
- **한 줄 요약:** 쇼츠(숏폼) 동영상을 단계별 검토·승인 방식으로 자동 생성·관리하는 소규모 멀티유저 로컬 웹앱.

---

## 1. 목표 & 범위

### 목표
주제를 입력하면 **대본 → 음성 → 자막 → 영상 합성**의 파이프라인을 통해 쇼츠 영상을 생성하고,
각 단계를 사람이 **검토·수정·승인**하며 관리할 수 있는 웹앱을 만든다.

### 확정된 요구사항
| 항목 | 결정 |
|------|------|
| 사용자 범위 | 소규모 멀티유저 (자율 회원가입 + 관리자 승인) |
| 자동화 수준 | 단계별 검토 후 진행 (각 단계 승인/수정/재생성) |
| 기술 스택 | Python + FastAPI 백엔드 / Vite + React 프론트 |
| 실행 환경 | 지금은 로컬 PC를 서버로, 추후 클라우드 이전 → **배포 독립적 설계** |
| 영상 스타일 | 슬라이드/텍스트, 스톡 영상+자막, AI 생성 이미지 (교체 가능한 렌더러) |
| 예산 | 무료/저비용 우선(Edge-TTS·로컬 Whisper·무료 스톡), 유료는 나중에 교체 |
| 업로드 | 지금은 다운로드만 (업로드는 미래 확장) |
| DB | PostgreSQL |
| 인증 | 이메일+비밀번호, httpOnly 쿠키 JWT |
| 권한 | member / admin 2단계 role |

### 비범위 (YAGNI)
- 플랫폼 자동 업로드(유튜브/틱톡) — 미래 확장 지점만 마련
- 과금/결제, 대규모 멀티테넌시
- 모바일/데스크톱 네이티브 앱

---

## 2. 아키텍처 (접근법 A: 경량 모놀리식)

### 시스템 개요
```
[React UI] ←HTTP/SSE→ [FastAPI 앱] ──작업 등록──▶ [PostgreSQL: users/projects/stages/assets]
                           │                              ▲
                           │                              │ 상태 갱신
                           ▼                              │
                     [백그라운드 워커(procrastinate)] ─단계 실행─┘
                           │
              ┌────────────┼────────────┬─────────────┐
              ▼            ▼            ▼             ▼
          [대본]        [음성]        [자막]        [영상렌더]
          Provider     Provider     Provider      Provider
          (Claude)    (Edge-TTS)   (Whisper)   (ffmpeg/스타일)
                           │
                           ▼
                    [파일 저장소 (utils/storage: 로컬↔S3)]
                storage/projects/{user_id}/{project_id}/...
```

- **인프라는 PostgreSQL 하나**로 통일: 데이터 저장 + 작업 큐(procrastinate, LISTEN/NOTIFY) 모두 Postgres 사용 → Redis 불필요.
- 로컬은 `docker compose up -d db`로 Postgres 기동, 앱/워커 실행.

### 3계층 분리 (핵심 설계 원칙)
```
providers/  ── 업무단 (도메인 작업: "대본을 만든다")     ← 자주 바뀜
core/       ── 오케스트레이션 (파이프라인·워커·상태머신)   ← 가끔 바뀜
utils/      ── 순수 기술 헬퍼 (도메인 지식 없음)          ← 안정적, 광범위 재사용
```
- **의존성은 항상 아래로만 흐른다.** `utils/`는 위 계층을 절대 import하지 않음 → 순환 참조 방지, 테스트 용이.
- 공통 영역(core)은 `Provider.run(ctx)` **인터페이스(계약)** 만 알고, 실제 구현(Claude/Edge-TTS/ffmpeg)은 모른다.

### 디렉토리 구조
```
studio/
├─ app/
│  ├─ main.py                # FastAPI 진입점
│  ├─ config.py              # .env 설정 로딩
│  ├─ db.py                  # asyncpg 엔진/세션
│  ├─ models.py              # Project, Stage, Asset (SQLModel)
│  ├─ api/                   # 라우터: projects, stages, files, sse
│  ├─ auth/                  # 인증 (아래 4장)
│  │  ├─ router.py           # /auth/register, login, logout, refresh
│  │  ├─ security.py         # 해시·JWT 인코딩/디코딩
│  │  ├─ deps.py             # current_user, require_admin
│  │  └─ models.py           # User
│  ├─ core/
│  │  ├─ pipeline.py         # 단계 정의 & 상태 머신
│  │  └─ worker.py           # procrastinate 태스크
│  ├─ providers/             # 업무단
│  │  ├─ base.py             # Provider 인터페이스, 레지스트리
│  │  ├─ script/claude.py
│  │  ├─ voice/edge_tts.py · elevenlabs.py
│  │  ├─ captions/whisper.py
│  │  └─ render/slideshow.py · stock.py · ai_image.py
│  ├─ queries/                # 쿼리 전용 계층 (아래 "쿼리 관리" 절 참고)
│  │  ├─ __init__.py         # aiosql.from_path(...)로 *.sql 로드
│  │  └─ (엔티티별 .sql 파일 추가: projects.sql · stages.sql ...)
│  └─ utils/                 # 기술 공통층
│     ├─ ffmpeg.py           # 명령 빌더·실행(9:16 크롭·자막 번인·오디오 믹스)
│     ├─ files.py · srt.py · http.py · retry.py · media.py
│     ├─ storage.py          # 로컬↔S3 저장 어댑터
│     └─ logging.py
├─ web/                      # Vite + React
│  ├─ layout/Sidebar         # role 기반 조건부 메뉴
│  ├─ pages/                 # dashboard, projects, settings, admin/*
│  └─ lib/auth               # 현재 사용자·role 상태
├─ alembic/                  # DB 마이그레이션
├─ storage/projects/         # 산출물(사용자별 분리)
├─ tests/
├─ docker-compose.yml        # Postgres
├─ Dockerfile
├─ .env.example
└─ pyproject.toml
```

---

## 3. 데이터 모델 & 파이프라인 상태 머신

### 데이터 모델
```
User ──1:N──▶ Project ──1:N──▶ Stage ──1:N──▶ Asset
                 └─ settings (JSONB: 스타일·provider 선택·목소리 등)
```

#### 공통 테이블 규칙 (모든 테이블 적용)
- **PK:** 모든 테이블의 `id`는 **정수(BIGINT) 자동 증가(IDENTITY)**.
- **감사(audit) 컬럼:** 모든 테이블은 아래 4개를 **공통 상속**(`BaseEntity` 믹스인).
  - `created_at` 생성일시 · `updated_at` 수정일시
  - `created_by` 생성자 · `updated_by` 수정자 (둘 다 `users.id` FK)
- `created_by`/`updated_by`는 앱 계층에서 **현재 로그인 사용자(current_user)** 로 자동 채움(SQLAlchemy 이벤트 리스너 또는 서비스 계층). 시스템/시드 생성분은 `NULL` 허용.
- **시간대(타임존):** 모든 일시 컬럼은 **naive `TIMESTAMP`(timezone 정보 없음)** 로, **저장 시점부터 현지 로컬 벽시계 시각**(기본 `Asia/Seoul`, KST)을 담는다.
  - 계산 위치: 애플리케이션(Python) 쪽에서 `app/utils/time.py`의 `now_local()`이 `APP_TIMEZONE` 기준 현재 벽시계 시각을 계산해 값으로 채움(`created_at`은 `default_factory`, `updated_at`은 `onupdate`). DB 서버 시각(`now()`)에 의존하지 않음.
  - 기본 타임존은 `.env`의 `APP_TIMEZONE=Asia/Seoul`로 설정(변경 가능). 이 값을 바꾸면 이후 저장되는 값도 그 타임존 벽시계 기준으로 바뀜.
  - **트레이드오프(의도적으로 감수):** UTC 저장 방식(클라우드 이전·다지역·서머타임에 유리)보다 로컬시간 그대로 저장하는 쪽을 선택함. 여러 타임존 사용자가 생기거나 서버를 다른 지역으로 옮길 경우, 과거 데이터의 재해석/마이그레이션이 필요할 수 있음을 인지하고 진행.

```python
class BaseEntity(SQLModel):             # 공통 믹스인 (자체는 테이블 아님)
    id: int = Field(primary_key=True)   # BIGINT, 자동 증가(IDENTITY)
    created_at: datetime                # 생성일시 (naive, 로컬 벽시계 시각)
    updated_at: datetime                # 수정일시 (naive, 수정 시 로컬 벽시계로 갱신)
    created_by: int | None              # 생성자  FK → users.id
    updated_by: int | None              # 수정자  FK → users.id

class Project(BaseEntity, table=True):
    owner_id: int                       # FK → users.id (데이터 격리)
    title: str
    topic: str                          # 주제/프롬프트
    status: str = "draft"               # draft|running|review|done|failed|archived
    current_stage: str = "script"
    settings: dict (JSONB)              # 스타일·provider 선택 등
    # id, created_at/by, updated_at/by → BaseEntity 상속

class Stage(BaseEntity, table=True):
    project_id: int                     # FK → projects.id
    name: str                           # script|voice|captions|render
    status: str = "pending"             # pending|running|needs_review|approved|failed
    provider: str                       # 사용한 provider 이름
    output: dict (JSONB)                # 산출 요약
    error: str | None
    started_at / finished_at
    # id, created_at/by, updated_at/by → BaseEntity 상속

class Asset(BaseEntity, table=True):
    stage_id: int                       # FK → stages.id
    kind: str                           # script_json|audio|srt|video|image
    path: str
    meta: dict (JSONB)                  # 길이·해상도·크기 등
    # id, created_at/by, updated_at/by → BaseEntity 상속
```

> 에러 코드/메시지는 DB 테이블로 관리하지 않는다. 아래 "7. 에러 처리" 절 참고.

### 쿼리 관리 (aiosql + `.sql` 파일)
- **역할 분리:** SQLModel(`BaseEntity`/`Project`/`Stage`/`Asset` 등)은 **테이블·컬럼 정의(스키마)** 와 **Alembic 마이그레이션**에만 사용한다. 실제 조회·등록·수정·삭제 쿼리는 ORM 쿼리빌더(`select(...)` 등)로 짜지 않고, **`app/queries/*.sql` 파일에 이름 붙여 작성**하고 [aiosql](https://github.com/nackjicholson/aiosql)로 로드해서 호출한다.
- **파일 구조:** 엔티티별로 `.sql` 파일 하나(`projects.sql`, `stages.sql` ...). 하위 디렉토리를 만들면 그 디렉토리명으로 네임스페이스가 생긴다(`queries.<dir>.<name>`).
- **쿼리 문법 예:**
  ```sql
  -- name: find_by_id(id)^
  SELECT id, title, status, created_at, updated_at
  FROM projects
  WHERE id = :id;
  ```
  (`^`=단건 조회, 접미사 없음=다건 조회, `!`=변경계, `<!`=INSERT...RETURNING)
- **커넥션 연결(핵심):** aiosql은 raw `asyncpg` 커넥션에서 동작하므로, SQLAlchemy `AsyncSession`과의 트랜잭션을 반드시 공유해야 한다(안 그러면 같은 요청/테스트 안에서 ORM으로 쓴 값을 aiosql 쿼리가 못 보거나, 커밋 전 상태가 꼬일 수 있음). `app/db.py`의 `raw_connection(session)` 헬퍼가 `await session.connection()` → `await conn.get_raw_connection()` → `.driver_connection`(SQLAlchemy 2.0 공식 API)으로 **같은 트랜잭션의 raw 커넥션**을 꺼내준다. 테스트의 SAVEPOINT 격리도 그대로 적용됨(검증 완료).
  ```python
  from app.db import raw_connection
  from app.queries import queries

  async def find_project(session, project_id):
      conn = await raw_connection(session)
      return await queries.find_by_id(conn, id=project_id)
  ```
- **인코딩 주의:** Windows(cp949 로케일)에서 `aiosql.from_path(...)`가 기본 인코딩으로 파일을 읽으면 한글 주석에서 `UnicodeDecodeError`가 난다(이전 `alembic.ini`와 같은 종류의 문제). 항상 `encoding="utf-8"`을 명시한다.

### 파이프라인 단계
```
script ──▶ voice ──▶ captions ──▶ render ──▶ (done)
```

### Stage 상태 머신 (단계별 검토)
```
pending ──[워커 실행]──▶ running ──┬─성공─▶ needs_review
                                    └─실패─▶ failed ──[재시도]──▶ pending

needs_review ──[승인]──▶ approved ──▶ (다음 단계 pending 등록)
     ├──[수정]──▶ 편집 후 재실행 ──▶ running
     └──[재생성]──▶ pending (다른 provider·설정)
```

### 동작 흐름
1. 프로젝트 생성 → `script` 단계 `pending` 큐 등록
2. 워커가 실행 → `running` → Claude 대본 생성 → `needs_review`
3. 사용자 검토 → 승인/수정/재생성
4. 승인 시 다음 단계 자동 등록 → 반복
5. 마지막 `render` 승인 → 프로젝트 `done` → mp4 다운로드

### 실시간 진행 표시
- 워커 상태 변경 → **SSE**로 UI 푸시(진행률 %). 폴링보다 가볍고 로컬·클라우드 동일 동작.

### 멱등성
- 각 단계는 멱등하게 설계 → 재생성 시 새 Asset으로 교체(이력 보존 옵션).

---

## 4. 인증 (Authentication)

### 라이브러리
- 비밀번호 해시: **argon2-cffi**(또는 bcrypt)
- 토큰: **PyJWT**
- 검증: Pydantic / 의존성 주입: FastAPI `Depends`

### User 모델
```python
class User(BaseEntity, table=True):   # BaseEntity 상속 (id·감사컬럼 공통)
    email: str (unique, index)
    password_hash: str                # 평문 저장 금지
    role: str = "member"              # member | admin
    status: str = "pending"           # pending | active | disabled | rejected
    approved_at: datetime | None
    approved_by: int | None           # FK → users.id (승인 관리자)
    # id, created_at/by, updated_at/by → BaseEntity 상속
    #  (users의 created_by/updated_by는 users.id 자기참조, NULL 허용)
```

### 가입·승인 흐름 (자율 가입 + 관리자 승인)
```
[사용자] POST /auth/register {email, password}
   → 이메일 중복검사 → argon2 해시 → User(status="pending") 생성
   → "관리자 승인 후 로그인 가능" 안내

[관리자] GET /admin/users?status=pending  (대기 목록)
   ├─ 승인: POST /admin/users/{id}/approve → status="active"
   └─ 거절: POST /admin/users/{id}/reject  → status="rejected"

[사용자] POST /auth/login
   status 검사: active→성공 / pending→403 / rejected→403 / disabled→403
```
- **최초 admin**은 시드 스크립트(`.env`의 `ADMIN_EMAIL/PASSWORD`, status=active, role=admin)로 생성.
- 관리자 알림: 관리자 페이지에 **대기 인원 배지** 표시(추가 인프라 불필요). 이메일 알림은 미래 확장.

### 로그인·세션 (httpOnly 쿠키 JWT)
```
POST /auth/login {email, password}
 ① User 조회(없으면 401) ② argon2.verify(실패 401)
 ③ status != active → 403  ④ JWT 발급
     access_token (15~30분, user·role 포함)
     refresh_token (7~14일, DB 저장/회전)
 ⑤ Set-Cookie: httpOnly, Secure, SameSite=Lax
```
- **httpOnly 쿠키**: JS 접근 차단 → XSS 토큰 탈취 방어. (CSRF는 SameSite + 토큰으로 방어)
- 갱신: `POST /auth/refresh`로 access 재발급 + refresh 회전(탈취 재사용 탐지).
- 로그아웃: 쿠키 삭제 + DB refresh_token 무효화.

### 인가 (의존성 주입)
```python
async def current_user(request, db) -> User:      # 쿠키 JWT 검증 → User 주입
def require_admin(user=Depends(current_user)):    # role != admin → 403
```
- 일반 라우트: `current_user`, 관리자 라우트(`/admin/*`): `require_admin`.

### 보안 체크리스트
| 위협 | 방어 |
|------|------|
| 비밀번호 유출 | argon2 해시+솔트 |
| XSS 토큰 탈취 | httpOnly·Secure 쿠키 |
| CSRF | SameSite=Lax + CSRF 토큰 |
| 무차별 대입 | 로그인/가입 rate limit |
| 계정 열거 | 실패 메시지 통일 |
| 토큰 위조 | 서버 시크릿 서명 |
| 권한 상승 | 전 라우트 current_user/require_admin 강제 |
| 데이터 격리 | 모든 쿼리 owner_id 필터(admin만 우회) |

---

## 5. 통합 UI 구조 (역할 기반 메뉴)

**관리자 사이트를 별도로 만들지 않는다.** 단일 앱에서 역할에 따라 메뉴만 가감.

```
공통 사이드바(모든 사용자):
  📊 대시보드   🎬 프로젝트   ⚙️ 설정

관리자에게만 추가로 표시(role == admin):
  🛡️ 관리자 ▼
     ├─ 가입 승인 (대기 N)   ├─ 사용자 관리
     ├─ 전체 프로젝트         └─ 시스템 설정
```

### URL 구조 (한 앱 안)
```
/dashboard
/projects  /projects/new  /projects/{id}
/settings
/admin/approvals  /admin/users  /admin/projects  /admin/system   ← admin 가드
```

### 이중 방어
- 프론트: `user.role`로 메뉴·라우트 조건부 렌더(admin 가드).
- 백엔드: `/admin/*`는 URL 직접 접근해도 `require_admin`으로 403. **보안은 항상 서버에서 강제.**

---

## 6. Provider 인터페이스 & 단계별 구현

### 공통 계약
```python
class StageContext:
    project: Project
    settings: dict          # 스타일·옵션
    inputs: dict            # 이전 단계 산출물
    workdir: Path
    on_progress: Callable   # 진행률 → SSE

class StageResult:
    assets: list[Asset]
    output: dict

class Provider(ABC):
    stage: str; name: str
    async def run(self, ctx: StageContext) -> StageResult: ...
    def validate(self, settings: dict) -> None: ...   # 필요 키·API키 확인
```

### 레지스트리 (이름으로 조회)
```python
REGISTRY = {
  "script":   {"claude": ClaudeScript},
  "voice":    {"edge_tts": EdgeTTS, "elevenlabs": ElevenLabs},
  "captions": {"whisper": WhisperCaptions},
  "render":   {"slideshow": SlideshowRender, "stock": StockRender,
               "ai_image": AiImageRender},
}
```
- 새 도구 추가 = 클래스 1개 + 레지스트리 1줄. **core는 손대지 않음.**

### 단계별 초기 구현 (무료·저비용 우선)
| 단계 | 기본 Provider | 하는 일 | utils |
|------|--------------|---------|-------|
| script | claude | 주제 → 후킹형 대본(JSON) | http, retry |
| voice | edge_tts(무료) | 대본 → mp3 | files |
| captions | whisper(로컬) | mp3 → 단어별 srt | srt, media |
| render | slideshow/stock/ai_image | 자막·오디오·비주얼 합성 → 9:16 mp4 | ffmpeg, media, files |

### render 3종 (같은 입력→같은 출력, UI 드롭다운 교체)
- `slideshow.py`: 배경 + 큰 자막(가장 가벼움, 무료)
- `stock.py`: Pexels/Pixabay 무료 영상 검색 → 자막 오버레이
- `ai_image.py`: (선택 유료) 이미지 생성 → 켄번즈 효과 + 자막
- 공통 합성 로직(9:16·자막 번인·오디오 믹스)은 `utils/ffmpeg.py`에서 공유.

### 실패·검증
- `validate()`로 실행 전 필요한 키 확인 → 친절한 에러.
- `run()` 예외 → Stage.failed + error → UI 재시도.
- 외부 API는 `utils/retry.py` 백오프로 자동 재시도.

---

## 7. 에러 처리 · 설정

### 에러 처리
| 계층 | 방식 |
|------|------|
| Provider | 예외 → Stage.failed + error → UI 표시/재시도 |
| 외부 API | retry 백오프 + 타임아웃 |
| 워커 | procrastinate 재시도/데드레터, 트랜잭션으로 상태 일관성 |
| API | 전역 예외 핸들러 → 일관 JSON `{code, message}` |
| 검증 | 실행 전 validate()로 조기 실패 |

### 에러 코드 관리 (소스 코드 기반, DB 미사용)
- **DB 조회 없음:** 에러 코드/메시지를 DB 테이블에서 찾아오는 카탈로그·조회 프로세스는 두지 않는다. `ErrorCode` 모델·`/admin/error-codes` 관리 화면 모두 없음(이전 설계에서 제거됨).
- **각 업무단이 직접 지정:** 에러가 발생하는 지점(각 provider·라우터 등 업무 로직)이 `AppError(status_code, code, message)`처럼 **상태 코드·코드·메시지를 직접 채워서** 던진다. 서버는 이 값을 그대로 응답에 실을 뿐, 별도 조회를 하지 않는다.
- **자주 쓰는 에러는 `Errors` 헬퍼로:** `Errors.not_found()`, `Errors.bad_request(message)`처럼 자주 쓰는 조합을 미리 정의해 둔 정적 팩토리를 제공한다(코드/디폴트 메시지 고정, 메시지만 선택적으로 오버라이드). 헬퍼에 없는 조합은 `AppError`를 직접 던지면 된다.
- **디폴트는 소스 코드 상수:** `AppError`가 아닌 **정말 예상 못한 예외**(버그, 미처리 상황)가 터졌을 때만 쓰는 디폴트 에러(`DEFAULT_ERROR`)를 `app/utils/errors.py`에 **코드 상수로 고정**해 둔다. DB 조회·캐시·시드가 필요 없다.

```python
# app/utils/errors.py
class AppError(Exception):
    def __init__(self, status_code: int, code: str, message: str):
        self.status_code = status_code
        self.code = code
        self.message = message

class Errors:
    @staticmethod
    def not_found(message: str = "리소스를 찾을 수 없습니다.") -> AppError:
        return AppError(404, "RESOURCE_NOT_FOUND", message)

    @staticmethod
    def bad_request(message: str = "잘못된 요청입니다.") -> AppError:
        return AppError(400, "BAD_REQUEST", message)

    @staticmethod
    def conflict(message: str = "이미 존재하는 리소스입니다.") -> AppError:
        return AppError(409, "CONFLICT", message)

    @staticmethod
    def forbidden(message: str = "접근 권한이 없습니다.") -> AppError:
        return AppError(403, "FORBIDDEN", message)

    @staticmethod
    def unauthorized(message: str = "인증이 필요합니다.") -> AppError:
        return AppError(401, "UNAUTHORIZED", message)

    @staticmethod
    def invalid_id(message: str = "유효하지 않은 ID입니다.") -> AppError:
        return AppError(400, "INVALID_ID", message)

DEFAULT_ERROR = ResolvedError(code="UNKNOWN_ERROR", message="알 수 없는 오류가 발생했습니다.", status_code=500)
```
```python
# app/main.py — 두 개의 전역 예외 핸들러
@app.exception_handler(AppError)               # 업무단이 직접 채운 값 그대로 응답
async def app_error_handler(request, exc):
    return JSONResponse(exc.status_code, {"code": exc.code, "message": exc.message})

@app.exception_handler(Exception)              # 예상 못한 예외 → 소스 상수 DEFAULT_ERROR
async def unhandled_exception_handler(request, exc):
    logger.exception(...)
    return JSONResponse(DEFAULT_ERROR.status_code, {"code": DEFAULT_ERROR.code, "message": DEFAULT_ERROR.message})
```
- 응답 형식은 항상 `{"code", "message"}`로 동일(전역 규칙 유지), 다만 **값의 출처가 DB가 아니라 코드**로 바뀐 것.

### 설정 (12-factor, 배포 독립)
```
DATABASE_URL, JWT_SECRET
STORAGE_BACKEND=local (→ 나중에 s3), STORAGE_PATH
ANTHROPIC_API_KEY, PEXELS_API_KEY(선택), ELEVENLABS_API_KEY(선택)
ADMIN_EMAIL / ADMIN_PASSWORD (최초 관리자 시드)
CORS_ORIGINS, SECURE_COOKIES(로컬=false, 클라우드=true)
APP_TIMEZONE=Asia/Seoul   # DB 저장값 자체의 기준 로컬 타임존(naive TIMESTAMP)
```
- 저장소는 `utils/storage.py` 뒤에 → 로컬 디스크 ↔ S3 무코드 교체.
- 로컬/클라우드 차이는 `.env`만으로 흡수. 시크릿은 git 미포함(`.env.example`만 커밋).

---

## 8. 테스트 전략

| 종류 | 대상 | 도구 |
|------|------|------|
| 단위 | utils/*(ffmpeg 빌드, srt, retry), provider 로직 | pytest |
| 통합 | API + DB(테스트 Postgres), 인증·인가·격리 | pytest + httpx + testcontainers |
| Provider | 외부 API는 **fake provider**로 파이프라인 흐름 검증(과금 없이) | pytest fixtures |
| 상태 머신 | 단계 전이 정확성 | pytest |
| E2E(선택) | 가입→승인→생성→단계 진행→다운로드 | Playwright |

- 외부 API·ffmpeg는 인터페이스 뒤 → **fake provider**로 빠르고 비용 없는 테스트.
- TDD로 각 단계 테스트 먼저 작성.

---

## 9. 확장 로드맵 (미래)
| 원하는 것 | 작업량 |
|-----------|--------|
| ElevenLabs 고품질 음성 | voice/elevenlabs.py + 레지스트리 1줄 |
| 유튜브 자동 업로드 | upload/ provider + 파이프라인 단계 1개 |
| 새 영상 템플릿 | render/에 파일 1개 |
| 클라우드 이전 | .env + storage 어댑터(S3) 교체, 코드 변경 없음 |
| S3 파일 저장 | STORAGE_BACKEND=s3 |
```
