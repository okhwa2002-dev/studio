# 파이프라인 첫 세로 슬라이스 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** `Project` 생성 → `script` 단계를 fake provider로 동기 실행 → 검토(승인/재생성)까지 관통하는 파이프라인 첫 세로 슬라이스를 구현한다.

**Architecture:** 상위 설계의 3계층(`api → core → providers`)을 처음으로 구현한다. `api/projects.py`가 요청 안에서 `core.pipeline.run_stage`를 동기 호출하고, core는 `Provider` 계약만 알며, `providers/script/fake.py`가 실제 대본 JSON을 만든다. 산출물은 `Stage.output`(JSONB)에 저장한다.

**Tech Stack:** Python 3 · FastAPI · SQLModel(스키마) · aiosql + asyncpg(쿼리) · Alembic · pytest + testcontainers · Vite + React + react-router + Tailwind.

## Global Constraints

- **모든 API는 `/api` 하위.** 라우터는 도메인 경로(`/projects`)만 정의하고, `app/main.py`가 `prefix="/api"`로 등록한다. 프론트 `api` 클라이언트는 `/projects`처럼 넘기면 자동으로 `/api`를 붙인다.
- **상태 문자열은 대문자 상수** (`DRAFT`,`PENDING`,`NEEDS_REVIEW` …). 단계 이름은 provider 레지스트리 키와 맞춰 소문자(`script`).
- **쿼리는 aiosql `.sql` 파일 + `raw_connection(session)`** 로 SQLAlchemy 세션과 같은 트랜잭션 공유. `aiosql.from_path`는 이미 `encoding="utf-8"`로 로드됨(기존 `app/queries/__init__.py`).
- **JSONB 취급(중요):** aiosql은 raw asyncpg 커넥션에서 동작하므로 dict를 자동 직렬화하지 않는다. **쓸 때** 파라미터를 `json.dumps(value)` 문자열로 넘기고 SQL에서 `:col::jsonb`로 캐스트한다. **읽을 때** asyncpg가 jsonb를 문자열로 돌려주므로 `json.loads`로 되돌린다. (경계에서만 변환)
- **시간은 `app.utils.time.now_local()`** 로 채운다(DB `now()` 사용 금지). 감사 컬럼은 기존 `app/models/base.py`의 `*_field()` 헬퍼로 각 모델 본문 맨 아래에 명시 선언.
- **데이터 격리:** project 관련 모든 조회는 `owner_id == current_user.id` 확인. 불일치/없음은 통일 `Errors.not_found()`(존재를 숨겨 열거 방지).
- **자동 커밋 금지:** 코드 작업 후 git 커밋은 각 태스크의 마지막 스텝에서 명시적으로 수행(이 계획의 스텝대로). 사용자 저장소 관례상 임의 커밋 금지.
- **참조 스펙:** `docs/superpowers/specs/2026-07-15-pipeline-first-slice-design.md`

---

### Task 1: 상수 + Project/Stage 모델

**Files:**
- Modify: `app/constants.py`
- Create: `app/models/project.py`
- Create: `app/models/stage.py`
- Modify: `app/models/__init__.py`
- Test: `tests/test_pipeline_models.py`

**Interfaces:**
- Produces:
  - `app.constants.ProjectStatus` (`DRAFT`,`REVIEW`,`DONE`), `StageName` (`SCRIPT="script"`), `StageStatus` (`PENDING`,`RUNNING`,`NEEDS_REVIEW`,`APPROVED`,`FAILED`)
  - `app.models.project.Project` (테이블 `projects`), `app.models.stage.Stage` (테이블 `stages`)
  - 두 모델이 `SQLModel.metadata`에 등록됨(테스트 `create_all`이 픽업)

- [ ] **Step 1: 실패 테스트 작성** — `tests/test_pipeline_models.py`

```python
from sqlmodel import SQLModel

import app.models  # noqa: F401  (모든 모델을 metadata에 등록)
from app.constants import ProjectStatus, StageName, StageStatus
from app.models.project import Project
from app.models.stage import Stage


def test_status_constants_are_uppercase():
    assert ProjectStatus.DRAFT == "DRAFT"
    assert ProjectStatus.DONE == "DONE"
    assert StageStatus.NEEDS_REVIEW == "NEEDS_REVIEW"
    assert StageName.SCRIPT == "script"  # 단계명은 레지스트리 키와 맞춰 소문자


def test_project_and_stage_tables_registered():
    tables = SQLModel.metadata.tables
    assert "projects" in tables
    assert "stages" in tables


def test_project_defaults():
    p = Project(owner_id=1, title="t", topic="주제")
    assert p.status == ProjectStatus.DRAFT
    assert p.current_stage == StageName.SCRIPT
    assert p.settings == {}


def test_stage_defaults():
    s = Stage(project_id=1, name=StageName.SCRIPT, provider="fake")
    assert s.status == StageStatus.PENDING
    assert s.output == {}
    assert s.attempt == 0
```

- [ ] **Step 2: 테스트 실패 확인**

Run: `python -m pytest tests/test_pipeline_models.py -v`
Expected: FAIL — `ModuleNotFoundError: app.models.project` / `ImportError: ProjectStatus`

- [ ] **Step 3: 상수 추가** — `app/constants.py` 파일 끝에 추가

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

- [ ] **Step 4: Project 모델 작성** — `app/models/project.py`

```python
from datetime import datetime
from typing import Optional

from sqlalchemy import BigInteger
from sqlalchemy.dialects.postgresql import JSONB
from sqlmodel import Field

from app.constants import ProjectStatus, StageName
from app.models.base import (
    BaseEntity,
    created_at_field,
    created_by_field,
    updated_at_field,
    updated_by_field,
)


class Project(BaseEntity, table=True):
    __tablename__ = "projects"
    __table_args__ = {"comment": "쇼츠 생성 프로젝트"}

    owner_id: int = Field(
        sa_type=BigInteger,
        foreign_key="users.id",
        index=True,
        sa_column_kwargs={"comment": "소유자 (FK: users.id, 데이터 격리)"},
    )
    title: str = Field(sa_column_kwargs={"comment": "프로젝트 제목"})
    topic: str = Field(sa_column_kwargs={"comment": "주제/프롬프트"})
    status: str = Field(
        default=ProjectStatus.DRAFT,
        sa_column_kwargs={"comment": "상태: DRAFT | REVIEW | DONE"},
    )
    current_stage: str = Field(
        default=StageName.SCRIPT,
        sa_column_kwargs={"comment": "현재 단계 이름 (예: script)"},
    )
    settings: dict = Field(
        default_factory=dict,
        sa_type=JSONB,
        sa_column_kwargs={"nullable": False, "comment": "스타일·provider 선택 등 (JSONB)"},
    )

    created_at: Optional[datetime] = created_at_field()
    created_by: Optional[int] = created_by_field(foreign_key="users.id")
    updated_at: Optional[datetime] = updated_at_field()
    updated_by: Optional[int] = updated_by_field(foreign_key="users.id")
```

- [ ] **Step 5: Stage 모델 작성** — `app/models/stage.py`

```python
from datetime import datetime
from typing import Optional

from sqlalchemy import BigInteger
from sqlalchemy.dialects.postgresql import JSONB
from sqlmodel import Field

from app.constants import StageStatus
from app.models.base import (
    BaseEntity,
    created_at_field,
    created_by_field,
    updated_at_field,
    updated_by_field,
)


class Stage(BaseEntity, table=True):
    __tablename__ = "stages"
    __table_args__ = {"comment": "파이프라인 단계 (script|voice|captions|render)"}

    project_id: int = Field(
        sa_type=BigInteger,
        foreign_key="projects.id",
        index=True,
        sa_column_kwargs={"comment": "소속 프로젝트 (FK: projects.id)"},
    )
    name: str = Field(sa_column_kwargs={"comment": "단계 이름 (예: script)"})
    provider: str = Field(sa_column_kwargs={"comment": "사용한 provider 이름 (예: fake)"})
    status: str = Field(
        default=StageStatus.PENDING,
        sa_column_kwargs={"comment": "상태: PENDING|RUNNING|NEEDS_REVIEW|APPROVED|FAILED"},
    )
    output: dict = Field(
        default_factory=dict,
        sa_type=JSONB,
        sa_column_kwargs={"nullable": False, "comment": "산출물 (script는 대본 JSON, JSONB)"},
    )
    error: Optional[str] = Field(
        default=None, sa_column_kwargs={"comment": "실패 메시지 (성공/미실행 시 NULL)"}
    )
    attempt: int = Field(
        default=0,
        sa_column_kwargs={"server_default": "0", "comment": "재생성 횟수 (재생성 시 +1)"},
    )
    started_at: Optional[datetime] = Field(
        default=None, sa_column_kwargs={"comment": "실행 시작 일시"}
    )
    finished_at: Optional[datetime] = Field(
        default=None, sa_column_kwargs={"comment": "실행 종료(성공/실패) 일시"}
    )

    created_at: Optional[datetime] = created_at_field()
    created_by: Optional[int] = created_by_field(foreign_key="users.id")
    updated_at: Optional[datetime] = updated_at_field()
    updated_by: Optional[int] = updated_by_field(foreign_key="users.id")
```

- [ ] **Step 6: 모델 등록** — `app/models/__init__.py` 전체를 아래로 교체

```python
from app.models.base import BaseEntity
from app.models.project import Project
from app.models.refresh_token import RefreshToken
from app.models.stage import Stage
from app.models.user import User

__all__ = ["BaseEntity", "Project", "RefreshToken", "Stage", "User"]
```

- [ ] **Step 7: 테스트 통과 확인**

Run: `python -m pytest tests/test_pipeline_models.py -v`
Expected: PASS (4 passed)

- [ ] **Step 8: 커밋**

```bash
git add app/constants.py app/models/project.py app/models/stage.py app/models/__init__.py tests/test_pipeline_models.py
git commit -m "기능: Project·Stage 모델과 파이프라인 상태 상수 추가"
```

---

### Task 2: Alembic 마이그레이션 (projects, stages)

**Files:**
- Create: `alembic/versions/<hash>_create_projects_and_stages.py` (autogenerate가 파일명·hash 생성)

**Interfaces:**
- Consumes: Task 1의 `Project`/`Stage` 모델(metadata)
- Produces: 실제 DB에 `projects`, `stages` 테이블

> 테스트는 `SQLModel.metadata.create_all`로 스키마를 만들므로 마이그레이션에 의존하지 않는다. 이 태스크는 **실 DB(docker compose Postgres)** 용이다. 먼저 로컬 Postgres가 떠 있어야 한다: `docker compose up -d db`.

- [ ] **Step 1: 마이그레이션 자동 생성**

Run: `python -m alembic revision --autogenerate -m "create projects and stages"`
Expected: `alembic/versions/<hash>_create_projects_and_stages.py` 생성. 로그에 `Detected added table 'projects'`, `Detected added table 'stages'`.

- [ ] **Step 2: 생성된 파일 검토·정리**

`upgrade()`에 `op.create_table('projects', ...)`와 `op.create_table('stages', ...)`가 있고 컬럼 순서가 **업무 컬럼 → 감사 컬럼(created_at/updated_at/created_by/updated_by)** 인지 확인한다. `users.id`가 자동 default(IDENTITY)를 드롭하려는 줄이 섞여 있으면(기존 `6e54c5b37edf` 마이그레이션의 NOTE 참조) **그 줄만 삭제**한다 — 이 마이그레이션은 두 테이블 생성만 담당한다. `downgrade()`는 `op.drop_table('stages')` → `op.drop_table('projects')` 순(FK 역순)인지 확인한다.

- [ ] **Step 3: 업그레이드 적용**

Run: `python -m alembic upgrade head`
Expected: 에러 없이 완료. `projects`, `stages` 테이블 생성됨.

- [ ] **Step 4: 다운그레이드 왕복 검증 후 재적용**

Run: `python -m alembic downgrade -1`
Expected: 두 테이블 삭제됨(에러 없음).
Run: `python -m alembic upgrade head`
Expected: 다시 생성됨.

- [ ] **Step 5: 커밋**

```bash
git add alembic/versions/
git commit -m "기능: projects·stages 테이블 마이그레이션 추가"
```

---

### Task 3: Provider 계약 (base.py)

**Files:**
- Create: `app/providers/__init__.py` (빈 파일)
- Create: `app/providers/base.py`
- Test: `tests/test_provider_base.py`

**Interfaces:**
- Produces:
  - `StageContext(topic: str, settings: dict = {}, inputs: dict = {}, attempt: int = 0)` (dataclass)
  - `StageResult(output: dict)` (dataclass)
  - `Provider` (ABC): 클래스 속성 `stage: str`, `name: str`; `validate(self, settings: dict) -> None`; `async run(self, ctx: StageContext) -> StageResult`
  - `REGISTRY: dict[str, dict[str, type[Provider]]]`
  - `get_provider(stage: str, name: str) -> Provider` — 없으면 `AppError(500, "PROVIDER_NOT_FOUND", ...)`

- [ ] **Step 1: 실패 테스트 작성** — `tests/test_provider_base.py`

```python
import pytest

from app.providers.base import Provider, StageContext, StageResult, get_provider
from app.utils.errors import AppError


class _Dummy(Provider):
    stage = "script"
    name = "dummy"

    async def run(self, ctx: StageContext) -> StageResult:
        return StageResult(output={"echo": ctx.topic})


def test_stage_context_defaults():
    ctx = StageContext(topic="주제")
    assert ctx.settings == {}
    assert ctx.inputs == {}
    assert ctx.attempt == 0


@pytest.mark.asyncio
async def test_provider_run_contract():
    result = await _Dummy().run(StageContext(topic="hello"))
    assert isinstance(result, StageResult)
    assert result.output == {"echo": "hello"}


def test_get_provider_unknown_raises_apperror():
    with pytest.raises(AppError) as exc:
        get_provider("script", "does-not-exist")
    assert exc.value.status_code == 500
    assert exc.value.code == "PROVIDER_NOT_FOUND"
```

- [ ] **Step 2: 테스트 실패 확인**

Run: `python -m pytest tests/test_provider_base.py -v`
Expected: FAIL — `ModuleNotFoundError: app.providers.base`

- [ ] **Step 3: 빈 패키지 파일 생성** — `app/providers/__init__.py`

```python
```

- [ ] **Step 4: base.py 작성** — `app/providers/base.py`

```python
from abc import ABC, abstractmethod
from dataclasses import dataclass, field

from app.utils.errors import AppError


@dataclass
class StageContext:
    """단계 실행에 필요한 입력. (파일 workdir·SSE on_progress는 해당 단계 도입 시 확장)"""

    topic: str
    settings: dict = field(default_factory=dict)
    inputs: dict = field(default_factory=dict)  # 이전 단계 산출물 (script엔 비어있음)
    attempt: int = 0  # 재생성 횟수 → provider 출력 변주 seed


@dataclass
class StageResult:
    output: dict  # Stage.output 에 저장될 산출 (script는 대본 JSON)


class Provider(ABC):
    stage: str
    name: str

    def validate(self, settings: dict) -> None:
        """실행 전 필요한 키·API키 확인. 기본은 no-op."""

    @abstractmethod
    async def run(self, ctx: StageContext) -> StageResult:
        ...


# 새 도구 추가 = 클래스 1개 + 여기 1줄. core는 손대지 않는다.
from app.providers.script.fake import FakeScript  # noqa: E402

REGISTRY: dict[str, dict[str, type[Provider]]] = {
    "script": {"fake": FakeScript},
}


def get_provider(stage: str, name: str) -> Provider:
    providers = REGISTRY.get(stage, {})
    cls = providers.get(name)
    if cls is None:
        raise AppError(500, "PROVIDER_NOT_FOUND", f"provider를 찾을 수 없습니다: {stage}/{name}")
    return cls()
```

> 주의: `base.py`가 `FakeScript`를 import하고 `FakeScript`(Task 4)가 `base.py`의 `Provider`를 import한다. 순환을 피하려고 `Provider`/`StageContext`/`StageResult` **정의 뒤에서** `FakeScript`를 import한다(위 순서 유지). Task 3 단독으로는 import가 실패하므로, Task 4의 파일을 먼저 만든 뒤 Step 5를 실행한다. 아래 Step 4b가 그 순서를 강제한다.

- [ ] **Step 4b: Task 4의 fake.py를 먼저 생성**

Task 4의 Step 3까지(파일 생성) 수행한 뒤 이 태스크로 돌아온다. (두 파일이 함께 있어야 import가 성립)

- [ ] **Step 5: 테스트 통과 확인**

Run: `python -m pytest tests/test_provider_base.py -v`
Expected: PASS (3 passed)

- [ ] **Step 6: 커밋** — Task 4와 함께 커밋(Task 4 Step 6에서 수행)

---

### Task 4: FakeScript provider

**Files:**
- Create: `app/providers/script/__init__.py` (빈 파일)
- Create: `app/providers/script/fake.py`
- Test: `tests/test_provider_script_fake.py`

**Interfaces:**
- Consumes: `app.providers.base.Provider`, `StageContext`, `StageResult`
- Produces: `FakeScript` — `stage="script"`, `name="fake"`; `run(ctx)`가 아래 스키마의 대본 JSON을 담은 `StageResult` 반환
  - 출력 스키마: `{"title": str, "hook": str, "scenes": [{"index": int, "narration": str, "on_screen": str}], "estimated_duration_sec": int}`
  - 같은 `(topic, attempt)`면 항상 같은 출력(결정적). `attempt`가 다르면 `hook`·`scenes` 문구가 달라짐.

- [ ] **Step 1: 실패 테스트 작성** — `tests/test_provider_script_fake.py`

```python
import pytest

from app.providers.base import StageContext, StageResult
from app.providers.script.fake import FakeScript


@pytest.mark.asyncio
async def test_output_schema():
    result = await FakeScript().run(StageContext(topic="바다 거북"))
    assert isinstance(result, StageResult)
    out = result.output
    assert out["title"].startswith("바다 거북")
    assert isinstance(out["hook"], str) and out["hook"]
    assert isinstance(out["scenes"], list) and len(out["scenes"]) >= 1
    first = out["scenes"][0]
    assert set(first.keys()) == {"index", "narration", "on_screen"}
    assert first["index"] == 1
    assert isinstance(out["estimated_duration_sec"], int) and out["estimated_duration_sec"] > 0


@pytest.mark.asyncio
async def test_deterministic_for_same_topic_and_attempt():
    a = await FakeScript().run(StageContext(topic="주제", attempt=0))
    b = await FakeScript().run(StageContext(topic="주제", attempt=0))
    assert a.output == b.output


@pytest.mark.asyncio
async def test_regeneration_changes_output():
    a = await FakeScript().run(StageContext(topic="주제", attempt=0))
    b = await FakeScript().run(StageContext(topic="주제", attempt=1))
    assert a.output != b.output
```

- [ ] **Step 2: 테스트 실패 확인**

Run: `python -m pytest tests/test_provider_script_fake.py -v`
Expected: FAIL — `ModuleNotFoundError: app.providers.script.fake`

- [ ] **Step 3: 파일 생성** — `app/providers/script/__init__.py` (빈 파일)

```python
```

그리고 `app/providers/script/fake.py`:

```python
from app.providers.base import Provider, StageContext, StageResult

# 재생성(attempt)마다 톤을 바꿔 산출물이 눈에 띄게 달라지되, 같은 attempt면 항상 동일.
_TONES = ["호기심 자극형", "충격 사실형", "공감 스토리형", "질문 던지기형"]


class FakeScript(Provider):
    """외부 호출 없이 결정적 대본 JSON을 만드는 개발/테스트용 provider."""

    stage = "script"
    name = "fake"

    async def run(self, ctx: StageContext) -> StageResult:
        tone = _TONES[ctx.attempt % len(_TONES)]
        scenes = [
            {
                "index": i,
                "narration": f"[{tone}] {ctx.topic}에 대한 {i}번째 핵심 포인트입니다.",
                "on_screen": f"{ctx.topic} · 포인트 {i}",
            }
            for i in range(1, 4)
        ]
        output = {
            "title": f"{ctx.topic} — 60초 쇼츠",
            "hook": f"[{tone}] 3초 안에 {ctx.topic}의 반전을 보여드립니다.",
            "scenes": scenes,
            "estimated_duration_sec": 45,
        }
        return StageResult(output=output)
```

- [ ] **Step 4: 테스트 통과 확인**

Run: `python -m pytest tests/test_provider_script_fake.py tests/test_provider_base.py -v`
Expected: PASS (6 passed) — base.py의 `REGISTRY` import도 이제 성립.

- [ ] **Step 5: 전체 provider 테스트 재확인**

Run: `python -m pytest tests/test_provider_base.py tests/test_provider_script_fake.py -v`
Expected: PASS

- [ ] **Step 6: 커밋 (Task 3 + Task 4 함께)**

```bash
git add app/providers/ tests/test_provider_base.py tests/test_provider_script_fake.py
git commit -m "기능: Provider 계약(base)과 FakeScript provider 추가"
```

---

### Task 5: 상태 머신 순수 함수 (core/pipeline 전이 규칙)

**Files:**
- Create: `app/core/__init__.py` (빈 파일)
- Create: `app/core/pipeline.py` (이 태스크에선 전이 규칙만; 오케스트레이션은 Task 6에서 추가)
- Test: `tests/test_pipeline_state_machine.py`

**Interfaces:**
- Produces:
  - `STAGE_ORDER: list[str]` = `["script"]`
  - `ALLOWED_TRANSITIONS: dict[str, set[str]]`
  - `can_transition(frm: str, to: str) -> bool`

- [ ] **Step 1: 실패 테스트 작성** — `tests/test_pipeline_state_machine.py`

```python
from app.constants import StageStatus
from app.core.pipeline import STAGE_ORDER, can_transition


def test_stage_order():
    assert STAGE_ORDER == ["script"]


def test_allowed_transitions():
    assert can_transition(StageStatus.PENDING, StageStatus.RUNNING)
    assert can_transition(StageStatus.RUNNING, StageStatus.NEEDS_REVIEW)
    assert can_transition(StageStatus.RUNNING, StageStatus.FAILED)
    assert can_transition(StageStatus.NEEDS_REVIEW, StageStatus.APPROVED)
    assert can_transition(StageStatus.NEEDS_REVIEW, StageStatus.PENDING)  # 재생성
    assert can_transition(StageStatus.FAILED, StageStatus.PENDING)  # 재시도


def test_denied_transitions():
    assert not can_transition(StageStatus.PENDING, StageStatus.APPROVED)
    assert not can_transition(StageStatus.APPROVED, StageStatus.RUNNING)
    assert not can_transition(StageStatus.NEEDS_REVIEW, StageStatus.RUNNING)
    assert not can_transition(StageStatus.RUNNING, StageStatus.APPROVED)
```

- [ ] **Step 2: 테스트 실패 확인**

Run: `python -m pytest tests/test_pipeline_state_machine.py -v`
Expected: FAIL — `ModuleNotFoundError: app.core.pipeline`

- [ ] **Step 3: 빈 패키지 파일 생성** — `app/core/__init__.py`

```python
```

- [ ] **Step 4: pipeline.py 전이 규칙 작성** — `app/core/pipeline.py`

```python
from app.constants import StageStatus

STAGE_ORDER: list[str] = ["script"]  # voice/captions/render 미구현

# Stage.status 허용 전이. 여기 없는 전이는 모두 금지(잘못된 요청 → 409).
ALLOWED_TRANSITIONS: dict[str, set[str]] = {
    StageStatus.PENDING: {StageStatus.RUNNING},
    StageStatus.RUNNING: {StageStatus.NEEDS_REVIEW, StageStatus.FAILED},
    StageStatus.NEEDS_REVIEW: {StageStatus.APPROVED, StageStatus.PENDING},  # 승인 / 재생성
    StageStatus.FAILED: {StageStatus.PENDING},  # 재시도
    StageStatus.APPROVED: set(),  # 이 슬라이스의 종착
}


def can_transition(frm: str, to: str) -> bool:
    return to in ALLOWED_TRANSITIONS.get(frm, set())
```

- [ ] **Step 5: 테스트 통과 확인**

Run: `python -m pytest tests/test_pipeline_state_machine.py -v`
Expected: PASS (3 passed)

- [ ] **Step 6: 커밋**

```bash
git add app/core/__init__.py app/core/pipeline.py tests/test_pipeline_state_machine.py
git commit -m "기능: Stage 상태 머신 전이 규칙(core/pipeline) 추가"
```

---

### Task 6: 쿼리 + 오케스트레이션 (run/approve/regenerate)

**Files:**
- Create: `app/queries/projects.sql`
- Create: `app/queries/stages.sql`
- Modify: `app/core/pipeline.py` (오케스트레이션 함수 추가)
- Test: `tests/test_pipeline_run_stage.py`

**Interfaces:**
- Consumes: `app.db.raw_connection`, `app.queries.queries`, `app.providers.base.get_provider`/`StageContext`, `app.utils.time.now_local`, `app.utils.errors.AppError`, Task 5의 `can_transition`
- Produces (모두 `app.core.pipeline`):
  - `decode_stage(row: dict | Record) -> dict` — asyncpg row의 `output`(jsonb 문자열)을 dict로 되돌린 새 dict 반환
  - `async run_stage(session, project: dict, stage: dict, actor_id: int) -> dict` — pending/failed에서만 실행, 성공 시 NEEDS_REVIEW(output 저장)·예외 시 FAILED(error 저장). 갱신된 stage(dict, output 디코드됨) 반환. 잘못된 상태면 `AppError(409, "STAGE_CONFLICT", …)`
  - `async approve_stage(session, project: dict, stage: dict, actor_id: int) -> None` — NEEDS_REVIEW→APPROVED, 프로젝트 DONE
  - `async regenerate_stage(session, project: dict, stage: dict, actor_id: int) -> dict` — NEEDS_REVIEW→PENDING(attempt+1) 후 `run_stage` 재호출, 갱신된 stage 반환
- aiosql 쿼리(이름): `insert_project`, `find_project_by_id`, `list_projects_by_owner`, `update_project_status`, `insert_stage`, `find_stage`, `list_stages_by_project`, `update_stage_run`, `update_stage_status`

> `project`/`stage` dict는 aiosql이 돌려준 row를 `dict(row)`한 것이며, `project["settings"]`와 `stage["output"]`은 **이미 dict로 디코드된 상태**로 넘어온다고 가정한다(디코드는 `decode_stage`/API 경계에서 수행). `run_stage`는 `project["topic"]`, `stage["attempt"]`, `stage["status"]`, `stage["id"]`, `stage["name"]`, `stage["provider"]`를 읽는다.

- [ ] **Step 1: 실패 테스트 작성** — `tests/test_pipeline_run_stage.py`

```python
import json

import pytest

from app.constants import ProjectStatus, StageName, StageStatus
from app.core import pipeline
from app.db import raw_connection
from app.queries import queries
from app.utils.errors import AppError
from app.utils.time import now_local


async def _seed_project_and_stage(session, *, status=StageStatus.PENDING, attempt=0):
    conn = await raw_connection(session)
    now = now_local()
    # owner FK 충족용 사용자 하나
    from app.auth.security import hash_password
    from app.constants import UserRole, UserStatus
    from app.models.user import User

    user = User(email="owner@example.com", password_hash=hash_password("pw12345"),
                role=UserRole.MEMBER, status=UserStatus.ACTIVE)
    session.add(user)
    await session.commit()
    await session.refresh(user)

    project_id = await queries.insert_project(
        conn, owner_id=user.id, title="t", topic="바다 거북",
        status=ProjectStatus.DRAFT, current_stage=StageName.SCRIPT, settings=json.dumps({}),
        created_at=now, updated_at=now, created_by=user.id, updated_by=user.id,
    )
    stage_id = await queries.insert_stage(
        conn, project_id=project_id, name=StageName.SCRIPT, provider="fake",
        status=status, output=json.dumps({}), error=None, attempt=attempt,
        started_at=None, finished_at=None,
        created_at=now, updated_at=now, created_by=user.id, updated_by=user.id,
    )
    await session.commit()
    project = pipeline.decode_stage(dict(await queries.find_project_by_id(conn, id=project_id)))
    stage = pipeline.decode_stage(dict(await queries.find_stage(conn, project_id=project_id, name=StageName.SCRIPT)))
    return user.id, project, stage


@pytest.mark.asyncio
async def test_run_stage_success_sets_needs_review(db_session):
    actor, project, stage = await _seed_project_and_stage(db_session)
    updated = await pipeline.run_stage(db_session, project, stage, actor_id=actor)
    assert updated["status"] == StageStatus.NEEDS_REVIEW
    assert updated["output"]["title"].startswith("바다 거북")
    assert updated["error"] is None


@pytest.mark.asyncio
async def test_run_stage_rejects_non_pending(db_session):
    actor, project, stage = await _seed_project_and_stage(db_session, status=StageStatus.APPROVED)
    with pytest.raises(AppError) as exc:
        await pipeline.run_stage(db_session, project, stage, actor_id=actor)
    assert exc.value.status_code == 409


@pytest.mark.asyncio
async def test_approve_stage_marks_project_done(db_session):
    actor, project, stage = await _seed_project_and_stage(db_session)
    ran = await pipeline.run_stage(db_session, project, stage, actor_id=actor)
    await pipeline.approve_stage(db_session, project, ran, actor_id=actor)
    conn = await raw_connection(db_session)
    proj = await queries.find_project_by_id(conn, id=project["id"])
    stg = await queries.find_stage(conn, project_id=project["id"], name=StageName.SCRIPT)
    assert proj["status"] == ProjectStatus.DONE
    assert stg["status"] == StageStatus.APPROVED


@pytest.mark.asyncio
async def test_regenerate_increments_attempt_and_reruns(db_session):
    actor, project, stage = await _seed_project_and_stage(db_session)
    ran = await pipeline.run_stage(db_session, project, stage, actor_id=actor)
    regen = await pipeline.regenerate_stage(db_session, project, ran, actor_id=actor)
    assert regen["status"] == StageStatus.NEEDS_REVIEW
    assert regen["attempt"] == 1
    assert regen["output"] != ran["output"]  # attempt 변주로 내용이 달라짐
```

- [ ] **Step 2: 테스트 실패 확인**

Run: `python -m pytest tests/test_pipeline_run_stage.py -v`
Expected: FAIL — `AttributeError: module 'app.core.pipeline' has no attribute 'decode_stage'` (또는 aiosql 쿼리 없음)

- [ ] **Step 3: projects.sql 작성** — `app/queries/projects.sql`

```sql
-- name: insert_project<!
INSERT INTO projects (owner_id, title, topic, status, current_stage, settings,
                      created_at, updated_at, created_by, updated_by)
VALUES (:owner_id, :title, :topic, :status, :current_stage, :settings::jsonb,
        :created_at, :updated_at, :created_by, :updated_by)
RETURNING id;

-- name: find_project_by_id^
SELECT id, owner_id, title, topic, status, current_stage, settings,
       created_at, updated_at
FROM projects
WHERE id = :id;

-- name: list_projects_by_owner
SELECT id, owner_id, title, topic, status, current_stage, created_at, updated_at
FROM projects
WHERE owner_id = :owner_id
ORDER BY created_at DESC, id DESC;

-- name: update_project_status!
UPDATE projects
SET status = :status,
    current_stage = :current_stage,
    updated_at = :updated_at,
    updated_by = :updated_by
WHERE id = :id;
```

- [ ] **Step 4: stages.sql 작성** — `app/queries/stages.sql`

```sql
-- name: insert_stage<!
INSERT INTO stages (project_id, name, provider, status, output, error, attempt,
                    started_at, finished_at,
                    created_at, updated_at, created_by, updated_by)
VALUES (:project_id, :name, :provider, :status, :output::jsonb, :error, :attempt,
        :started_at, :finished_at,
        :created_at, :updated_at, :created_by, :updated_by)
RETURNING id;

-- name: find_stage^
SELECT id, project_id, name, provider, status, output, error, attempt,
       started_at, finished_at, created_at, updated_at
FROM stages
WHERE project_id = :project_id AND name = :name;

-- name: list_stages_by_project
SELECT id, project_id, name, provider, status, output, error, attempt,
       started_at, finished_at, created_at, updated_at
FROM stages
WHERE project_id = :project_id
ORDER BY id ASC;

-- name: update_stage_run!
UPDATE stages
SET status = :status,
    output = :output::jsonb,
    error = :error,
    attempt = :attempt,
    started_at = :started_at,
    finished_at = :finished_at,
    updated_at = :updated_at,
    updated_by = :updated_by
WHERE id = :id;

-- name: update_stage_status!
UPDATE stages
SET status = :status,
    updated_at = :updated_at,
    updated_by = :updated_by
WHERE id = :id;
```

- [ ] **Step 5: 오케스트레이션 추가** — `app/core/pipeline.py` 끝에 추가 (상단 import도 추가)

파일 상단 import 블록을 아래로 교체:

```python
import json

from app.constants import ProjectStatus, StageStatus
from app.db import raw_connection
from app.providers.base import StageContext, get_provider
from app.queries import queries
from app.utils.errors import AppError
from app.utils.time import now_local
```

파일 끝에 함수 추가:

```python
def decode_stage(row: dict) -> dict:
    """asyncpg가 문자열로 돌려준 jsonb 컬럼(output/settings)을 dict로 되돌린 새 dict."""
    row = dict(row)
    for key in ("output", "settings"):
        value = row.get(key)
        if isinstance(value, str):
            row[key] = json.loads(value)
    return row


async def run_stage(session, project: dict, stage: dict, actor_id: int) -> dict:
    if stage["status"] not in (StageStatus.PENDING, StageStatus.FAILED):
        raise AppError(409, "STAGE_CONFLICT", "이미 실행 중이거나 검토 단계입니다.")

    conn = await raw_connection(session)
    started = now_local()
    provider = get_provider(stage["name"], stage["provider"])
    ctx = StageContext(
        topic=project["topic"],
        settings=project.get("settings", {}),
        inputs={},
        attempt=stage["attempt"],
    )
    try:
        result = await provider.run(ctx)
        status, output, error = StageStatus.NEEDS_REVIEW, result.output, None
    except Exception as exc:  # provider 예외는 삼키지 않고 상태로 기록
        status, output, error = StageStatus.FAILED, {}, str(exc)

    await queries.update_stage_run(
        conn, id=stage["id"], status=status, output=json.dumps(output), error=error,
        attempt=stage["attempt"], started_at=started, finished_at=now_local(),
        updated_at=now_local(), updated_by=actor_id,
    )
    await session.commit()
    updated = await queries.find_stage(conn, project_id=project["id"], name=stage["name"])
    return decode_stage(updated)


async def approve_stage(session, project: dict, stage: dict, actor_id: int) -> None:
    if not can_transition(stage["status"], StageStatus.APPROVED):
        raise AppError(409, "STAGE_CONFLICT", "승인할 수 없는 상태입니다.")

    conn = await raw_connection(session)
    now = now_local()
    await queries.update_stage_status(
        conn, id=stage["id"], status=StageStatus.APPROVED, updated_at=now, updated_by=actor_id
    )
    # script가 마지막 구현 단계라 프로젝트를 DONE으로 둔다.
    # 향후 여러 단계가 생기면 이 부분은 "다음 단계 PENDING 등록 + current_stage 갱신"으로 교체한다.
    await queries.update_project_status(
        conn, id=project["id"], status=ProjectStatus.DONE, current_stage=stage["name"],
        updated_at=now, updated_by=actor_id,
    )
    await session.commit()


async def regenerate_stage(session, project: dict, stage: dict, actor_id: int) -> dict:
    if not can_transition(stage["status"], StageStatus.PENDING):
        raise AppError(409, "STAGE_CONFLICT", "재생성할 수 없는 상태입니다.")

    conn = await raw_connection(session)
    now = now_local()
    new_attempt = stage["attempt"] + 1
    await queries.update_stage_run(
        conn, id=stage["id"], status=StageStatus.PENDING, output=json.dumps({}), error=None,
        attempt=new_attempt, started_at=None, finished_at=None, updated_at=now, updated_by=actor_id,
    )
    await session.commit()
    reloaded = decode_stage(await queries.find_stage(conn, project_id=project["id"], name=stage["name"]))
    return await run_stage(session, project, reloaded, actor_id=actor_id)
```

- [ ] **Step 6: 테스트 통과 확인**

Run: `python -m pytest tests/test_pipeline_run_stage.py -v`
Expected: PASS (4 passed)

- [ ] **Step 7: 커밋**

```bash
git add app/queries/projects.sql app/queries/stages.sql app/core/pipeline.py tests/test_pipeline_run_stage.py
git commit -m "기능: 프로젝트/단계 쿼리와 run·approve·regenerate 오케스트레이션 추가"
```

---

### Task 7: API 라우터 (app/api/projects.py)

**Files:**
- Create: `app/api/projects.py`
- Modify: `app/main.py` (라우터 등록)
- Test: `tests/test_api_projects.py`

**Interfaces:**
- Consumes: `current_user`(dict, `user["id"]`), `get_db`, `raw_connection`, `queries`, `pipeline`, `Errors`, `now_local`, 상수
- Produces (HTTP, 모두 `/api` 접두 후):
  - `POST /projects` `{title, topic}` → 201, 본문 `{project, stages}`(상세)
  - `GET /projects` → `ProjectSummary[]`
  - `GET /projects/{project_id}` → `{project, stages}`
  - `POST /projects/{project_id}/stages/{name}/run` → `{project, stages}`
  - `POST /projects/{project_id}/stages/{name}/approve` → `{project, stages}`
  - `POST /projects/{project_id}/stages/{name}/regenerate` → `{project, stages}`
  - 소유 아님/없음 → 404, 잘못된 상태 전이 → 409, 미인증 → 401

- [ ] **Step 1: 실패 테스트 작성** — `tests/test_api_projects.py`

```python
from app.auth.security import hash_password
from app.constants import ProjectStatus, StageStatus, UserRole, UserStatus
from app.models.user import User


async def _login(client, db_session, email: str) -> User:
    user = User(email=email, password_hash=hash_password("pw12345"),
                role=UserRole.MEMBER, status=UserStatus.ACTIVE)
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    resp = await client.post("/api/auth/login", json={"email": email, "password": "pw12345"})
    assert resp.status_code == 200
    return user


async def test_requires_auth(client):
    resp = await client.get("/api/projects")
    assert resp.status_code == 401


async def test_create_project_seeds_pending_script_stage(client, db_session):
    await _login(client, db_session, "a@example.com")
    resp = await client.post("/api/projects", json={"title": "첫 프로젝트", "topic": "바다 거북"})
    assert resp.status_code == 201
    body = resp.json()
    assert body["project"]["status"] == ProjectStatus.DRAFT
    assert len(body["stages"]) == 1
    assert body["stages"][0]["name"] == "script"
    assert body["stages"][0]["status"] == StageStatus.PENDING


async def test_run_then_approve_flow(client, db_session):
    await _login(client, db_session, "b@example.com")
    pid = (await client.post("/api/projects", json={"title": "t", "topic": "우주"})).json()["project"]["id"]

    ran = await client.post(f"/api/projects/{pid}/stages/script/run")
    assert ran.status_code == 200
    stage = ran.json()["stages"][0]
    assert stage["status"] == StageStatus.NEEDS_REVIEW
    assert stage["output"]["title"].startswith("우주")

    approved = await client.post(f"/api/projects/{pid}/stages/script/approve")
    assert approved.status_code == 200
    assert approved.json()["stages"][0]["status"] == StageStatus.APPROVED
    assert approved.json()["project"]["status"] == ProjectStatus.DONE


async def test_regenerate_increments_attempt(client, db_session):
    await _login(client, db_session, "c@example.com")
    pid = (await client.post("/api/projects", json={"title": "t", "topic": "커피"})).json()["project"]["id"]
    await client.post(f"/api/projects/{pid}/stages/script/run")
    regen = await client.post(f"/api/projects/{pid}/stages/script/regenerate")
    assert regen.status_code == 200
    assert regen.json()["stages"][0]["attempt"] == 1
    assert regen.json()["stages"][0]["status"] == StageStatus.NEEDS_REVIEW


async def test_run_twice_conflicts(client, db_session):
    await _login(client, db_session, "d@example.com")
    pid = (await client.post("/api/projects", json={"title": "t", "topic": "산"})).json()["project"]["id"]
    await client.post(f"/api/projects/{pid}/stages/script/run")  # → NEEDS_REVIEW
    again = await client.post(f"/api/projects/{pid}/stages/script/run")
    assert again.status_code == 409


async def test_owner_isolation(client, db_session):
    owner = await _login(client, db_session, "owner@example.com")
    pid = (await client.post("/api/projects", json={"title": "t", "topic": "비밀"})).json()["project"]["id"]

    # 다른 사용자로 로그인(쿠키 교체) 후 접근 → 404
    await _login(client, db_session, "intruder@example.com")
    resp = await client.get(f"/api/projects/{pid}")
    assert resp.status_code == 404
    run = await client.post(f"/api/projects/{pid}/stages/script/run")
    assert run.status_code == 404
```

- [ ] **Step 2: 테스트 실패 확인**

Run: `python -m pytest tests/test_api_projects.py -v`
Expected: FAIL — 404 (라우트 없음) 또는 import 오류

- [ ] **Step 3: 라우터 작성** — `app/api/projects.py`

```python
import json

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import current_user
from app.constants import ProjectStatus, StageName, StageStatus
from app.core import pipeline
from app.db import get_db, raw_connection
from app.queries import queries
from app.utils.errors import Errors
from app.utils.time import now_local

router = APIRouter(prefix="/projects", tags=["projects"])


def _project_public(project: dict) -> dict:
    return {
        "id": project["id"],
        "title": project["title"],
        "topic": project["topic"],
        "status": project["status"],
        "current_stage": project["current_stage"],
        "created_at": project["created_at"].isoformat() if project.get("created_at") else None,
    }


def _stage_public(stage: dict) -> dict:
    return {
        "id": stage["id"],
        "name": stage["name"],
        "provider": stage["provider"],
        "status": stage["status"],
        "output": stage["output"],
        "error": stage["error"],
        "attempt": stage["attempt"],
    }


async def _load_owned_project(conn, project_id: int, user_id: int) -> dict:
    row = await queries.find_project_by_id(conn, id=project_id)
    if row is None or row["owner_id"] != user_id:
        raise Errors.not_found("프로젝트를 찾을 수 없습니다.")
    return pipeline.decode_stage(row)  # settings jsonb 디코드


async def _load_stage(conn, project_id: int, name: str) -> dict:
    row = await queries.find_stage(conn, project_id=project_id, name=name)
    if row is None:
        raise Errors.not_found("단계를 찾을 수 없습니다.")
    return pipeline.decode_stage(row)  # output jsonb 디코드


async def _detail(conn, project_id: int) -> dict:
    project = pipeline.decode_stage(await queries.find_project_by_id(conn, id=project_id))
    stage_rows = await queries.list_stages_by_project(conn, project_id=project_id)
    stages = [_stage_public(pipeline.decode_stage(r)) for r in stage_rows]
    return {"project": _project_public(project), "stages": stages}


class CreateProjectRequest(BaseModel):
    title: str
    topic: str


@router.post("", status_code=201)
async def create_project(
    body: CreateProjectRequest,
    user: dict = Depends(current_user),
    db: AsyncSession = Depends(get_db),
):
    conn = await raw_connection(db)
    now = now_local()
    project_id = await queries.insert_project(
        conn, owner_id=user["id"], title=body.title.strip(), topic=body.topic.strip(),
        status=ProjectStatus.DRAFT, current_stage=StageName.SCRIPT, settings=json.dumps({}),
        created_at=now, updated_at=now, created_by=user["id"], updated_by=user["id"],
    )
    await queries.insert_stage(
        conn, project_id=project_id, name=StageName.SCRIPT, provider="fake",
        status=StageStatus.PENDING, output=json.dumps({}), error=None, attempt=0,
        started_at=None, finished_at=None,
        created_at=now, updated_at=now, created_by=user["id"], updated_by=user["id"],
    )
    await db.commit()
    return await _detail(conn, project_id)


@router.get("")
async def list_projects(user: dict = Depends(current_user), db: AsyncSession = Depends(get_db)):
    conn = await raw_connection(db)
    rows = await queries.list_projects_by_owner(conn, owner_id=user["id"])
    return [_project_public(dict(r)) for r in rows]


@router.get("/{project_id}")
async def get_project(
    project_id: int, user: dict = Depends(current_user), db: AsyncSession = Depends(get_db)
):
    conn = await raw_connection(db)
    await _load_owned_project(conn, project_id, user["id"])
    return await _detail(conn, project_id)


@router.post("/{project_id}/stages/{name}/run")
async def run_stage(
    project_id: int, name: str, user: dict = Depends(current_user), db: AsyncSession = Depends(get_db)
):
    conn = await raw_connection(db)
    project = await _load_owned_project(conn, project_id, user["id"])
    stage = await _load_stage(conn, project_id, name)
    await pipeline.run_stage(db, project, stage, actor_id=user["id"])
    return await _detail(conn, project_id)


@router.post("/{project_id}/stages/{name}/approve")
async def approve_stage(
    project_id: int, name: str, user: dict = Depends(current_user), db: AsyncSession = Depends(get_db)
):
    conn = await raw_connection(db)
    project = await _load_owned_project(conn, project_id, user["id"])
    stage = await _load_stage(conn, project_id, name)
    await pipeline.approve_stage(db, project, stage, actor_id=user["id"])
    return await _detail(conn, project_id)


@router.post("/{project_id}/stages/{name}/regenerate")
async def regenerate_stage(
    project_id: int, name: str, user: dict = Depends(current_user), db: AsyncSession = Depends(get_db)
):
    conn = await raw_connection(db)
    project = await _load_owned_project(conn, project_id, user["id"])
    stage = await _load_stage(conn, project_id, name)
    await pipeline.regenerate_stage(db, project, stage, actor_id=user["id"])
    return await _detail(conn, project_id)
```

- [ ] **Step 4: 라우터 등록** — `app/main.py`

import 추가(다른 라우터 import 근처):

```python
from app.api.projects import router as projects_router
```

등록 추가(`admin_users_router` 등록 줄 아래):

```python
app.include_router(projects_router, prefix="/api")
```

- [ ] **Step 5: 테스트 통과 확인**

Run: `python -m pytest tests/test_api_projects.py -v`
Expected: PASS (7 passed)

- [ ] **Step 6: 백엔드 전체 회귀 확인**

Run: `python -m pytest -q`
Expected: 전체 PASS (기존 테스트 포함 회귀 없음)

- [ ] **Step 7: 커밋**

```bash
git add app/api/projects.py app/main.py tests/test_api_projects.py
git commit -m "기능: 프로젝트/단계 API(생성·실행·승인·재생성) 추가"
```

---

### Task 8: 프론트엔드 (목록·생성·상세)

**Files:**
- Create: `web/src/lib/projects.ts`
- Create: `web/src/pages/ProjectNew.tsx`
- Create: `web/src/pages/ProjectDetail.tsx`
- Modify: `web/src/pages/Projects.tsx` (플레이스홀더 → 실제 목록)
- Modify: `web/src/App.tsx` (라우트 2개 추가)

**Interfaces:**
- Consumes: `app.api.projects`의 HTTP 계약(Task 7), 기존 `api`(`web/src/lib/api.ts`)
- Produces: `projects` API 래퍼, 3개 페이지, `/projects/new`·`/projects/:id` 라우트

> 이 저장소에는 프론트 테스트 러너가 없다(모든 테스트가 pytest). 프론트는 **타입체크 빌드(`npm run build`)와 수동 스모크**로 검증한다.

- [ ] **Step 1: API 래퍼 작성** — `web/src/lib/projects.ts`

```ts
import { api } from './api'

export type ScriptScene = { index: number; narration: string; on_screen: string }
export type ScriptOutput = {
  title: string
  hook: string
  scenes: ScriptScene[]
  estimated_duration_sec: number
}
export type StageStatus = 'PENDING' | 'RUNNING' | 'NEEDS_REVIEW' | 'APPROVED' | 'FAILED'
export type ProjectStatus = 'DRAFT' | 'REVIEW' | 'DONE'

export type Stage = {
  id: number
  name: string
  provider: string
  status: StageStatus
  output: ScriptOutput | Record<string, never>
  error: string | null
  attempt: number
}

export type ProjectSummary = {
  id: number
  title: string
  topic: string
  status: ProjectStatus
  current_stage: string
  created_at: string
}

export type ProjectDetail = { project: ProjectSummary; stages: Stage[] }

export const projects = {
  list: () => api.get<ProjectSummary[]>('/projects'),
  create: (body: { title: string; topic: string }) => api.post<ProjectDetail>('/projects', body),
  detail: (id: number) => api.get<ProjectDetail>(`/projects/${id}`),
  run: (id: number, name: string) => api.post<ProjectDetail>(`/projects/${id}/stages/${name}/run`),
  approve: (id: number, name: string) =>
    api.post<ProjectDetail>(`/projects/${id}/stages/${name}/approve`),
  regenerate: (id: number, name: string) =>
    api.post<ProjectDetail>(`/projects/${id}/stages/${name}/regenerate`),
}

export const STAGE_BADGE: Record<StageStatus, { label: string; className: string }> = {
  PENDING: { label: '대기', className: 'bg-slate-100 text-slate-600' },
  RUNNING: { label: '실행 중', className: 'bg-blue-100 text-blue-800' },
  NEEDS_REVIEW: { label: '검토 필요', className: 'bg-yellow-100 text-yellow-800' },
  APPROVED: { label: '승인됨', className: 'bg-green-100 text-green-800' },
  FAILED: { label: '실패', className: 'bg-red-100 text-red-800' },
}

export function hasScript(output: Stage['output']): output is ScriptOutput {
  return 'title' in output
}
```

- [ ] **Step 2: 목록 페이지 교체** — `web/src/pages/Projects.tsx` 전체를 아래로 교체

```tsx
import { useCallback, useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { FormError } from '../components/FormError'
import { Table, type Column } from '../components/table/Table'
import { ApiError } from '../lib/api'
import { projects, type ProjectSummary } from '../lib/projects'

const UNKNOWN = '알 수 없는 오류가 발생했습니다.'

const PROJECT_STATUS_LABEL: Record<ProjectSummary['status'], string> = {
  DRAFT: '작성 중',
  REVIEW: '검토 중',
  DONE: '완료',
}

function formatDate(iso: string) {
  return iso.slice(0, 10)
}

export function Projects() {
  const [rows, setRows] = useState<ProjectSummary[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  const load = useCallback(() => {
    setLoading(true)
    setError(null)
    projects
      .list()
      .then(setRows)
      .catch((e) => setError(e instanceof ApiError ? e.message : UNKNOWN))
      .finally(() => setLoading(false))
  }, [])

  useEffect(() => {
    load()
  }, [load])

  const columns: Column<ProjectSummary>[] = [
    { header: '제목', cell: (p) => <Link to={`/projects/${p.id}`} className="text-slate-900 hover:underline">{p.title}</Link> },
    { header: '주제', cell: (p) => p.topic },
    { header: '상태', cell: (p) => PROJECT_STATUS_LABEL[p.status] },
    { header: '생성일', cell: (p) => formatDate(p.created_at), align: 'right' },
  ]

  return (
    <div>
      <div className="mb-4 flex items-center justify-between">
        <h1 className="text-lg font-semibold text-slate-900">프로젝트</h1>
        <Link
          to="/projects/new"
          className="rounded-md bg-slate-900 px-3 py-1.5 text-sm font-medium text-white"
        >
          새 프로젝트
        </Link>
      </div>

      {error && (
        <div className="mb-4">
          <FormError message={error} />
        </div>
      )}

      {loading ? (
        <div className="p-10 text-center text-sm text-slate-500">불러오는 중…</div>
      ) : (
        <Table columns={columns} rows={rows} rowKey={(p) => p.id} empty="아직 프로젝트가 없습니다." />
      )}
    </div>
  )
}
```

- [ ] **Step 3: 생성 페이지 작성** — `web/src/pages/ProjectNew.tsx`

```tsx
import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { FormError } from '../components/FormError'
import { TextField } from '../components/TextField'
import { ApiError } from '../lib/api'
import { projects } from '../lib/projects'

const UNKNOWN = '알 수 없는 오류가 발생했습니다.'

export function ProjectNew() {
  const navigate = useNavigate()
  const [title, setTitle] = useState('')
  const [topic, setTopic] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [submitting, setSubmitting] = useState(false)

  const submit = async (e: React.FormEvent) => {
    e.preventDefault()
    setSubmitting(true)
    setError(null)
    try {
      const detail = await projects.create({ title: title.trim(), topic: topic.trim() })
      navigate(`/projects/${detail.project.id}`)
    } catch (e) {
      setError(e instanceof ApiError ? e.message : UNKNOWN)
      setSubmitting(false)
    }
  }

  return (
    <div className="max-w-lg">
      <h1 className="mb-4 text-lg font-semibold text-slate-900">새 프로젝트</h1>
      <form onSubmit={submit} className="space-y-4">
        <TextField
          id="title"
          label="제목"
          required
          value={title}
          onChange={(e) => setTitle(e.target.value)}
        />
        <TextField
          id="topic"
          label="주제"
          required
          value={topic}
          onChange={(e) => setTopic(e.target.value)}
        />
        {error && <FormError message={error} />}
        <button
          type="submit"
          disabled={submitting || !title.trim() || !topic.trim()}
          className="rounded-md bg-slate-900 px-4 py-2 text-sm font-medium text-white disabled:opacity-50"
        >
          만들기
        </button>
      </form>
    </div>
  )
}
```

> **검증됨:** `TextField`는 네이티브 `<input>` props를 확장한다(`{label, error?, id, ...rest}`). `onChange`는 네이티브 `ChangeEventHandler`이므로 위처럼 `(e) => set...(e.target.value)`로 넘긴다(`Register.tsx`와 동일). `value`/`required`/`type`은 `...rest`로 전달된다.

- [ ] **Step 4: 상세 페이지 작성** — `web/src/pages/ProjectDetail.tsx`

```tsx
import { useCallback, useEffect, useState } from 'react'
import { useParams } from 'react-router-dom'
import { FormError } from '../components/FormError'
import { ApiError } from '../lib/api'
import { hasScript, projects, STAGE_BADGE, type ProjectDetail as Detail, type Stage } from '../lib/projects'

const UNKNOWN = '알 수 없는 오류가 발생했습니다.'

function StageBadge({ status }: { status: Stage['status'] }) {
  const badge = STAGE_BADGE[status]
  return (
    <span className={`rounded-full px-2 py-0.5 text-xs font-medium ${badge.className}`}>
      {badge.label}
    </span>
  )
}

function ScriptView({ stage }: { stage: Stage }) {
  if (!hasScript(stage.output)) return null
  const s = stage.output
  return (
    <div className="mt-4 space-y-3 rounded-md border border-slate-200 p-4">
      <div className="text-base font-semibold text-slate-900">{s.title}</div>
      <div className="text-sm text-slate-600">🎣 {s.hook}</div>
      <ol className="space-y-2">
        {s.scenes.map((scene) => (
          <li key={scene.index} className="text-sm">
            <span className="font-medium text-slate-800">#{scene.index}</span>{' '}
            <span className="text-slate-700">{scene.narration}</span>
            <div className="text-xs text-slate-400">화면: {scene.on_screen}</div>
          </li>
        ))}
      </ol>
      <div className="text-xs text-slate-400">예상 길이 {s.estimated_duration_sec}초</div>
    </div>
  )
}

export function ProjectDetail() {
  const { id } = useParams<{ id: string }>()
  const projectId = Number(id)
  const [detail, setDetail] = useState<Detail | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [acting, setActing] = useState(false)

  const load = useCallback(() => {
    setLoading(true)
    setError(null)
    projects
      .detail(projectId)
      .then(setDetail)
      .catch((e) => setError(e instanceof ApiError ? e.message : UNKNOWN))
      .finally(() => setLoading(false))
  }, [projectId])

  useEffect(() => {
    load()
  }, [load])

  const act = async (fn: () => Promise<Detail>) => {
    setActing(true)
    setError(null)
    try {
      setDetail(await fn())
    } catch (e) {
      setError(e instanceof ApiError ? e.message : UNKNOWN)
    } finally {
      setActing(false)
    }
  }

  if (loading) return <div className="p-10 text-center text-sm text-slate-500">불러오는 중…</div>
  if (!detail) return <FormError message={error ?? UNKNOWN} />

  const stage = detail.stages[0]

  return (
    <div className="max-w-2xl">
      <h1 className="text-lg font-semibold text-slate-900">{detail.project.title}</h1>
      <p className="mt-1 text-sm text-slate-500">주제: {detail.project.topic}</p>

      {error && <div className="mt-4"><FormError message={error} /></div>}

      <div className="mt-6 rounded-lg border border-slate-200 p-4">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2">
            <span className="font-medium text-slate-800">대본 (script)</span>
            <StageBadge status={stage.status} />
          </div>
          <div className="flex gap-2">
            {(stage.status === 'PENDING' || stage.status === 'FAILED') && (
              <button
                onClick={() => act(() => projects.run(projectId, stage.name))}
                disabled={acting}
                className="rounded-md bg-slate-900 px-3 py-1 text-xs font-medium text-white disabled:opacity-50"
              >
                실행
              </button>
            )}
            {stage.status === 'NEEDS_REVIEW' && (
              <>
                <button
                  onClick={() => act(() => projects.approve(projectId, stage.name))}
                  disabled={acting}
                  className="rounded-md bg-slate-900 px-3 py-1 text-xs font-medium text-white disabled:opacity-50"
                >
                  승인
                </button>
                <button
                  onClick={() => act(() => projects.regenerate(projectId, stage.name))}
                  disabled={acting}
                  className="rounded-md border border-slate-300 px-3 py-1 text-xs font-medium text-slate-700 hover:bg-slate-50 disabled:opacity-50"
                >
                  재생성
                </button>
              </>
            )}
          </div>
        </div>

        {stage.status === 'FAILED' && stage.error && (
          <div className="mt-3 text-sm text-red-700">오류: {stage.error}</div>
        )}
        {(stage.status === 'NEEDS_REVIEW' || stage.status === 'APPROVED') && <ScriptView stage={stage} />}
      </div>
    </div>
  )
}
```

- [ ] **Step 5: 라우트 추가** — `web/src/App.tsx`

import 추가(`Projects` import 근처):

```tsx
import { ProjectDetail } from './pages/ProjectDetail'
import { ProjectNew } from './pages/ProjectNew'
```

`<Route path="/projects" element={<Projects />} />` 아래에 두 줄 추가:

```tsx
          <Route path="/projects/new" element={<ProjectNew />} />
          <Route path="/projects/:id" element={<ProjectDetail />} />
```

- [ ] **Step 6: 타입체크 빌드**

Run: `cd web && npm run build`
Expected: 타입 에러 없이 빌드 성공. (에러가 나면 `TextField`/`Table`/`Column` 등 기존 컴포넌트의 실제 시그니처에 맞춰 수정)

- [ ] **Step 7: 린트**

Run: `cd web && npm run lint`
Expected: 통과 (기존 규칙 위반 없음)

- [ ] **Step 8: 수동 스모크 (선택이지만 권장)**

`docker compose up -d db` → `alembic upgrade head` → 백엔드(`uvicorn app.main:app`)와 프론트(`npm run dev`) 기동 → 로그인 → 프로젝트 → "새 프로젝트" 생성 → 상세에서 **실행** → 대본 표시 → **재생성**(문구 변화) → **승인**(상태 승인됨, 프로젝트 완료) 확인.

- [ ] **Step 9: 커밋**

```bash
git add web/src/lib/projects.ts web/src/pages/Projects.tsx web/src/pages/ProjectNew.tsx web/src/pages/ProjectDetail.tsx web/src/App.tsx
git commit -m "기능: 프로젝트 목록·생성·상세 화면과 단계 실행/검토 UI 추가"
```

---

## 최종 검증

- [ ] 백엔드 전체 테스트: `python -m pytest -q` → 전체 PASS
- [ ] 프론트 빌드+린트: `cd web && npm run build && npm run lint` → 통과
- [ ] 수동 스모크(Task 8 Step 8) 통과

## Self-Review 결과 (작성자 점검)

- **스펙 커버리지:** 데이터 모델(§3)→T1/T2, Provider(§4)→T3/T4, 상태 머신·오케스트레이션(§5)→T5/T6, API·쿼리(§6)→T6/T7, 프론트(§7)→T8, 에러 처리(§8)→T6/T7(409·404), 테스트(§9)→각 태스크. 누락 없음.
- **플레이스홀더:** 모든 코드/명령/기대출력 구체화. "적절히 처리" 류 없음.
- **타입 일관성:** `run_stage/approve_stage/regenerate_stage`가 `actor_id` 포함해 T6 정의와 T7 호출부 일치. `decode_stage`가 output/settings 모두 디코드. 쿼리 이름(`update_stage_run`에 `updated_by` 포함)이 T6 SQL과 core 호출부 일치. 프론트 `projects.*`가 모두 `ProjectDetail` 반환 → 상세 페이지 `setDetail` 일치.
- **프론트 시그니처 검증 완료:** `TextField`(네이티브 input props 확장, `onChange`는 이벤트 핸들러) 및 `Table`/`Column`(`../components/table/Table`, `cell: (row)=>ReactNode`, `align?`) 실제 구현과 일치 확인. 계획 코드 반영 완료.
