# 파이프라인 첫 세로 슬라이스 — 설계 문서 (Design Spec)

- **작성일:** 2026-07-15
- **프로젝트명:** studio
- **한 줄 요약:** 상위 설계(`2026-07-09-studio-design.md`)의 3계층(providers/core/api)과 Stage 상태 머신을 처음으로 살리는, 가장 얇은 세로 슬라이스. `Project` 생성 → `script` 단계를 **fake provider로 동기 실행** → 검토(승인/재생성).

---

## 1. 목표 & 범위

### 목표
파이프라인 전체(script→voice→captions→render)를 한 번에 만들지 않고, **하나의 단계(script)를 top-to-bottom으로 관통**하는 얇은 세로 슬라이스를 만든다. 이 슬라이스가 상위 설계의 핵심 seam을 처음으로 구현한다:
- **3계층 분리**: `providers/`(업무단) ↔ `core/`(오케스트레이션·상태머신) ↔ `api/`(라우트)
- **Stage 상태 머신**: `pending → running → needs_review → approved` (+ 재생성 경로)

### 확정된 범위 (이번 슬라이스에 포함)
| 항목 | 결정 |
|------|------|
| 단계 | `script` 하나만 |
| Provider | **fake** (외부 API·과금 없음, 결정적 출력) |
| 실행 방식 | **동기** (요청 안에서 `run_stage` 호출; 워커 없음) |
| 검토 액션 | **승인 + 재생성** (`needs_review→approved`, `needs_review→pending→running`) |
| 산출물 저장 | **`Stage.output` JSONB에 직접** (대본 JSON) |
| 실행 트리거 | **명시적 "실행" 버튼** → `POST .../run` |
| 테이블 | `projects` + `stages` 두 개만 |
| 데이터 격리 | 모든 쿼리 `owner_id` 확인 (불일치는 통일 404) |

### 비범위 (다음 슬라이스로 미룸, YAGNI)
- **워커(procrastinate)·큐·SSE** — 실행은 지금 동기. run 엔드포인트가 나중에 enqueue로 바뀌는 seam만 만들어 둔다.
- **실제 Claude provider** — fake와 같은 `Provider` 계약을 구현하는 것으로 나중에 교체(레지스트리 1줄).
- **voice / captions / render 단계** — `STAGE_ORDER`에 아직 없음.
- **Asset 테이블 · `utils/storage.py`** — 파일 산출물이 생기는 단계(voice/render)에서 도입. script는 작은 구조화 JSON이라 `Stage.output`이 자연스럽다.
- **수정(대본 직접 편집) 액션** — 승인/재생성만. 편집은 다음 슬라이스.
- **관리자 전체 프로젝트 보기** — 목록은 본인 것만.

---

## 2. 아키텍처 — 3계층 seam

```
[React: Projects / ProjectNew / ProjectDetail]
        │  HTTP (/api/projects ...)
        ▼
[app/api/projects.py]  ── 라우트·인증·소유권 가드 ──▶ core.run_stage 를 "동기" 호출
        │
        ▼
[app/core/pipeline.py] ── 상태 머신·오케스트레이션 (Provider 계약만 앎)
        │  get_provider("script","fake")
        ▼
[app/providers/script/fake.py] ── 업무단: 주제 → 대본 JSON (결정적)
        │
        ▼
[Stage.output JSONB]  (대본 저장)
```

- **의존성은 아래로만**: `api → core → providers`. `core`는 `Provider` 계약만 알고 fake 구현은 모른다.
- **동기↔비동기 전환점은 단 한 곳**: 지금은 `api`가 `core.run_stage`를 `await`로 직접 호출한다. 워커 도입 시 run 엔드포인트가 "즉시 실행" 대신 "태스크 enqueue"로 바뀌고, 워커가 **같은 `core.run_stage`** 를 호출한다. core/providers는 손대지 않는다.

---

## 3. 데이터 모델 & 마이그레이션

기존 `BaseEntity`(PK만 제공) + 감사 컬럼 명시 선언 패턴(`app/models/base.py`의 `*_field()` 헬퍼)을 그대로 따른다. JSONB는 `sqlalchemy.dialects.postgresql.JSONB`.

### `app/models/project.py` — `Project` (`projects`)
| 컬럼 | 타입 | 설명 |
|------|------|------|
| `owner_id` | BIGINT FK→users.id | 데이터 격리 |
| `title` | str | 프로젝트 제목 |
| `topic` | str | 주제/프롬프트 |
| `status` | str = `"DRAFT"` | 이 슬라이스: `DRAFT → REVIEW → DONE` |
| `current_stage` | str = `"script"` | 현재 단계 |
| `settings` | JSONB = `{}` | provider 선택 등(이번엔 사실상 비움) |
| 감사 4개 | | `created_at/by`, `updated_at/by` |

### `app/models/stage.py` — `Stage` (`stages`)
| 컬럼 | 타입 | 설명 |
|------|------|------|
| `project_id` | BIGINT FK→projects.id | 소속 프로젝트 |
| `name` | str | `"script"` |
| `provider` | str | `"fake"` |
| `status` | str = `"PENDING"` | `PENDING\|RUNNING\|NEEDS_REVIEW\|APPROVED\|FAILED` |
| `output` | JSONB = `{}` | **대본 JSON 저장 위치** |
| `error` | str \| None | 실패 메시지 |
| `attempt` | int = `0` | 재생성 횟수. 최초 생성 `0`, **재생성할 때마다 +1**. fake 출력 변주 seed |
| `started_at` | datetime \| None | 실행 시작 |
| `finished_at` | datetime \| None | 실행 종료(성공/실패) |
| 감사 4개 | | |

> **상태 문자열 대문자 규칙:** 기존 `UserRole`/`UserStatus`가 대문자 상수(`MEMBER`,`ACTIVE`)를 쓰므로 동일하게 `DRAFT`/`PENDING` 등 대문자로 저장한다. 단계 이름(`script`)은 provider 레지스트리 키와 일치해야 하므로 소문자.

### `app/constants.py` 추가
```python
class ProjectStatus:
    DRAFT = "DRAFT"
    REVIEW = "REVIEW"
    DONE = "DONE"

class StageName:
    SCRIPT = "script"

class StageStatus:
    PENDING = "PENDING"
    RUNNING = "RUNNING"
    NEEDS_REVIEW = "NEEDS_REVIEW"
    APPROVED = "APPROVED"
    FAILED = "FAILED"
```

### 마이그레이션
alembic revision 1개로 `projects` + `stages` 테이블 생성. 기존 마이그레이션 규칙(주석·명시 컬럼 순서)을 따른다.

---

## 4. Provider 계층 (`app/providers/`)

### `base.py`
```python
from abc import ABC, abstractmethod
from dataclasses import dataclass, field

@dataclass
class StageContext:
    topic: str
    settings: dict = field(default_factory=dict)
    inputs: dict = field(default_factory=dict)   # 이전 단계 산출물(script엔 비어있음)
    attempt: int = 0                              # 재생성 횟수 → fake 출력 변주 seed

@dataclass
class StageResult:
    output: dict                                  # Stage.output 에 저장될 산출(대본 JSON)

class Provider(ABC):
    stage: str
    name: str
    def validate(self, settings: dict) -> None:   # 필요 키·API키 확인(fake는 no-op)
        ...
    @abstractmethod
    async def run(self, ctx: StageContext) -> StageResult:
        ...

REGISTRY: dict[str, dict[str, type[Provider]]] = {
    "script": {"fake": FakeScript},
}

def get_provider(stage: str, name: str) -> Provider:
    # 없으면 AppError(설정 오류) — 사용자에게 친절한 메시지
    ...
```

> 상위 설계의 `StageContext`에 있던 `project`/`workdir`/`on_progress`(파일·SSE)는 **이번 슬라이스에서 의도적으로 제외**한다. 파일 산출물(voice/render)과 SSE가 필요해지는 단계에서 필드를 추가한다. `run(ctx) -> StageResult` 계약(seam)은 유지되므로 확장은 비파괴적.

### `script/fake.py` — `FakeScript`
- `stage = "script"`, `name = "fake"`
- `run(ctx)`: `ctx.topic`을 템플릿에 넣어 **결정적** 대본 JSON을 만든다. `ctx.attempt`를 variant로 사용해 **재생성 시 문구가 눈에 띄게 달라지되**, 같은 (topic, attempt)면 항상 같은 출력 → 테스트 안정.
- 외부 호출·랜덤·과금 없음.

**대본 JSON 스키마 (확정):**
```json
{
  "title": "<topic> — 60초 쇼츠",
  "hook": "3초 안에 시선을 잡는 첫 문장",
  "scenes": [
    { "index": 1, "narration": "나레이션 대사", "on_screen": "화면 자막/키워드" }
  ],
  "estimated_duration_sec": 45
}
```
- `narration`은 다음 단계 voice가 읽을 텍스트, `on_screen`은 captions/render가 쓸 화면 텍스트를 염두에 둔 필드. 이번 슬라이스에선 저장·표시만 한다.

---

## 5. Core 계층 (`app/core/pipeline.py`)

### 단계 정의
```python
STAGE_ORDER = ["script"]   # voice/captions/render 미구현
```

### 상태 머신 (Stage.status)
```python
ALLOWED_TRANSITIONS = {
    "PENDING":      {"RUNNING"},
    "RUNNING":      {"NEEDS_REVIEW", "FAILED"},
    "NEEDS_REVIEW": {"APPROVED", "PENDING"},   # 승인 / 재생성
    "FAILED":       {"PENDING"},               # 재시도
    "APPROVED":     set(),                     # 이 슬라이스의 종착
}

def can_transition(frm: str, to: str) -> bool:
    return to in ALLOWED_TRANSITIONS.get(frm, set())
```

### 오케스트레이션 함수
- **`async run_stage(session, project, stage)`**
  1. 가드: `stage.status`가 `PENDING` 또는 `FAILED`가 아니면 `AppError`(409 CONFLICT, "이미 실행 중이거나 검토 단계입니다").
  2. `PENDING→RUNNING` 전이, `started_at = now_local()`, DB 반영.
  3. `provider = get_provider(stage.name·provider)`, `ctx = StageContext(topic=project.topic, settings=project.settings, inputs={}, attempt=stage.attempt)`.
  4. `try`: `result = await provider.run(ctx)` → `output = result.output`, `status = NEEDS_REVIEW`, `finished_at`.
     `except Exception as e`: `status = FAILED`, `error = str(e)`, `finished_at`. (예외를 삼키지 않고 상태로 기록)
  5. `queries.update_stage_run(...)`로 원자적 반영.
- **`async approve_stage(session, project, stage)`**: 가드 `NEEDS_REVIEW→APPROVED`. `stage.status=APPROVED`. script가 **마지막 구현 단계**이므로 `project.status = DONE`.
  > **향후 교체 지점:** 여러 단계가 생기면 이 부분은 "다음 단계 `PENDING` 등록 + `project.current_stage` 갱신"으로 바뀐다. (주석으로 명시)
- **`async regenerate_stage(session, project, stage)`**: 가드 `NEEDS_REVIEW→PENDING`. `attempt += 1`, `status=PENDING`, `output={}`, `error=None`. 이어서 **같은 요청 안에서 `run_stage`를 재호출**(동기)하여 새 `NEEDS_REVIEW` 생성. → `NEEDS_REVIEW → PENDING → RUNNING → NEEDS_REVIEW` 전이를 관통.

---

## 6. API (`app/api/projects.py`)

모두 `/api` 하위, `current_user` 의존성 필수. 소유권: 조회한 project의 `owner_id != current_user.id`면 `Errors.not_found()`(존재 자체를 숨겨 열거 방지).

| 메서드 · 경로 | 동작 |
|---|---|
| `POST /api/projects` | `{title, topic}` → `Project`(DRAFT, current_stage=script) + `Stage`(script, PENDING, provider=fake) 생성. `owner_id=현재 사용자`. 생성된 project+stages 반환 |
| `GET /api/projects` | 본인 프로젝트 목록(`owner_id` 필터, `created_at DESC`) |
| `GET /api/projects/{id}` | 상세 + stages. 소유 아니면 404 |
| `POST /api/projects/{id}/stages/{name}/run` | `run_stage` 동기 실행 → 갱신된 stage 반환 |
| `POST /api/projects/{id}/stages/{name}/approve` | `approve_stage` → stage + project 반환 |
| `POST /api/projects/{id}/stages/{name}/regenerate` | `regenerate_stage`(재실행 포함) → stage 반환 |

- 요청/응답은 Pydantic 모델. 응답에서 감사 컬럼 등 불필요 필드는 제외하고 프론트가 쓰는 필드만 노출(기존 `/auth/me` 방식).
- `app/main.py`에 `projects_router`를 `prefix="/api"`로 등록.

### 쿼리 (`aiosql`, `encoding="utf-8"`, `raw_connection` 트랜잭션 공유)
- **`app/queries/projects.sql`**: `insert_project<!`, `find_project_by_id^`(owner_id 포함 반환), `list_projects_by_owner`, `update_project_status!`
- **`app/queries/stages.sql`**: `insert_stage<!`, `find_stage^`(project_id+name), `list_stages_by_project`, `update_stage_run!`(status·output·error·started_at·finished_at·attempt·updated_at), `update_stage_status!`

---

## 7. 프론트엔드 (`web/src/`)

기존 라우터·fetch 래퍼·페이지 패턴을 재사용한다.

- **`pages/Projects.tsx`**: `GET /api/projects` 목록(제목·주제·상태 뱃지) + "새 프로젝트" 버튼. 행 클릭 → 상세.
- **`pages/ProjectNew.tsx`**: `title`·`topic` 폼 → `POST /api/projects` → 상세로 이동.
- **`pages/ProjectDetail.tsx`**: `GET /api/projects/{id}` → script 단계 카드:
  - 상태 뱃지(`PENDING/RUNNING/NEEDS_REVIEW/APPROVED/FAILED`)
  - 상태별 버튼: `PENDING`·`FAILED` → **실행** / `NEEDS_REVIEW` → **승인**·**재생성** / `APPROVED` → "승인됨"
  - `NEEDS_REVIEW`·`APPROVED`일 때 `output` 대본 렌더(title·hook·scenes 목록)
  - `FAILED`일 때 `error` 표시
- 라우트 `/projects`, `/projects/new`, `/projects/:id` 추가(사이드바 "프로젝트" 메뉴는 이미 존재).

---

## 8. 에러 처리

상위 설계의 `Errors`/`AppError` 규칙을 그대로 사용(전역 핸들러가 `{code, message}`로 응답).
- 소유 아님 / 없음 → `Errors.not_found()`
- 잘못된 상태에서 실행/승인/재생성 → `AppError(409, "STAGE_CONFLICT", ...)` (자주 쓰면 `Errors`에 헬퍼 추가 검토)
- 없는 provider → 설정 오류 `AppError(500-계열 또는 400)` + 친절 메시지
- provider `run()` 예외 → 삼키지 않고 `Stage.FAILED` + `error`로 기록(사용자는 재실행 가능)

---

## 9. 테스트 전략 (TDD 먼저)

| 파일 | 대상 |
|---|---|
| `tests/test_providers_script_fake.py` | `FakeScript.run` 출력 스키마·결정성, `attempt` 변주로 출력이 달라짐 |
| `tests/test_pipeline_state_machine.py` | `can_transition` 허용/거부; `run_stage` happy(PENDING→NEEDS_REVIEW)·failure(예외 provider→FAILED); `approve_stage`(→APPROVED, project DONE); `regenerate_stage`(attempt 증가·재실행) |
| `tests/test_api_projects.py` (통합, 테스트 Postgres) | 인증 필수(401); 생성→실행→승인/재생성 흐름; **owner 격리(타인 프로젝트 접근 404)**; non-PENDING 실행 시 409 |

- 기존 `tests/conftest.py`(testcontainers Postgres, SAVEPOINT 격리)를 그대로 사용.
- 외부 의존성이 없어(fake·동기) 파이프라인 흐름 전체를 빠르고 비용 없이 검증.

---

## 10. 이 슬라이스가 남기는 seam (다음 단계 연결점)

| 미래 작업 | 이 슬라이스가 준비해 둔 것 |
|---|---|
| 실제 Claude script provider | `Provider` 계약 + 레지스트리 → `{"script": {"fake":…, "claude":…}}` 한 줄 |
| 워커(procrastinate)·비동기 | run 엔드포인트만 "즉시 실행 → enqueue"로, 워커가 같은 `core.run_stage` 호출 |
| voice/captions/render | `STAGE_ORDER` 확장 + `approve_stage`의 "다음 단계 등록"으로 교체 + Asset/storage 도입 |
| SSE 진행률 | `StageContext.on_progress` 필드 추가 + `run_stage`가 상태 변경 시 push |
