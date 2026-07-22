# 백그라운드 워커 + SSE Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 단계 실행을 HTTP 요청에서 떼어내 앱 내 asyncio 워커가 맡게 하고, 상태 전이와 진행률을 SSE로 UI에 푸시한다. 프로젝트 생성 시 "자동 진행"을 켜면 4단계가 검토 없이 끝까지 돈다.

**Architecture:** `stages` 테이블이 큐 역할을 하고(상태의 단일 출처는 항상 DB), 인메모리 `asyncio.Queue`에는 `stage_id`만 싣는다. 두 번의 원자적 CAS(`PENDING|FAILED → QUEUED`는 API가, `QUEUED → RUNNING`은 워커가)로 중복 실행을 구조적으로 막는다. 이벤트는 `app/core/events.py`의 인메모리 pub/sub을 거쳐 SSE 엔드포인트로 나간다.

**Tech Stack:** FastAPI(`lifespan`, `StreamingResponse`) · asyncio · asyncpg + aiosql · Alembic · React 19 + `EventSource`

**설계 문서:** [../specs/2026-07-21-worker-sse-design.md](../specs/2026-07-21-worker-sse-design.md)

## Global Constraints

- 기존 코드 규약을 그대로 따른다: 쿼리는 `app/queries/*.sql`에 이름 붙여 작성하고 aiosql로 호출한다. ORM 쿼리빌더를 쓰지 않는다.
- 계층 의존은 아래로만 흐른다: `api → core → providers → utils`. `utils`는 위 계층을 import하지 않는다.
- 주석과 사용자 노출 문구는 **한국어**. 주석은 "왜"를 적고 코드를 반복하지 않는다.
- 시각은 `app.utils.time.now_local()`로 만든다 (로컬 벽시계, timezone 정보 없음).
- 테스트는 `uv run pytest`로 돌린다. 프론트 검증은 `npm run lint` + `npm run build` (프론트에는 테스트 러너가 없다).
- 새 Python 의존성을 추가하지 않는다. procrastinate는 이번 범위 밖이다.
- 커밋은 각 Task 끝에서 한 번. 커밋 메시지는 기존 이력을 따라 한국어 접두어(`기능:` / `수정:` / `문서:` / `리팩터:`)를 쓴다.

---

## File Structure

| 파일 | 책임 |
|------|------|
| `app/constants.py` | `StageStatus.QUEUED` 추가 (수정) |
| `app/config.py` | `worker_concurrency` (수정) |
| `app/queries/stages.sql` | `queue_stage` · `claim_stage_run`(조건 변경) · `find_stage_by_id` · `fail_running_stages` · `list_queued_stage_ids` (수정) |
| `alembic/versions/<new>.py` | `stages.status` 컬럼 코멘트 갱신 (생성) |
| `app/core/pipeline.py` | 상태 머신 + 단계 실행 primitive (수정) |
| `app/core/events.py` | 인메모리 pub/sub + 마지막 진행률 캐시 (**생성**) |
| `app/core/views.py` | API 응답·SSE 이벤트가 공유하는 공개 표현 (**생성**) |
| `app/core/worker.py` | `StageWorker` — 큐·워커 루프·기동 복구·자동 연쇄 (**생성**) |
| `app/providers/base.py` | `StageContext.on_progress` 계약 (수정) |
| `app/providers/captions/whisper.py` | 세그먼트 단위 진행률 (수정) |
| `app/providers/script/*.py` · `voice/edge_tts.py` | 메시지 진행률 (수정) |
| `app/providers/render/slideshow.py` | ffmpeg 진행률 배선 (수정) |
| `app/utils/ffmpeg.py` | `-progress pipe:1` + 줄 파싱 (수정) |
| `app/api/projects.py` | SSE 엔드포인트 · 202 · `auto_run` (수정) |
| `app/main.py` | `lifespan`으로 워커 기동/종료 (수정) |
| `web/src/lib/events.ts` | `EventSource` 래퍼 + 백오프 재연결 (**생성**) |
| `web/src/lib/projects.ts` | `QUEUED` 배지 · `auto_run` · 진행률 타입 (수정) |
| `web/src/pages/projects/ProjectDetail.tsx` | 구독 · 진행률 UI (수정) |
| `web/src/pages/projects/NewProjectModal.tsx` | 자동 진행 체크박스 (수정) |

---

## Task 1: `QUEUED` 상태와 두 단계 CAS

**Files:**
- Modify: `app/constants.py`
- Modify: `app/queries/stages.sql`
- Modify: `app/core/pipeline.py:15-28`, `app/core/pipeline.py:84-126`
- Create: `alembic/versions/<generated>_add_queued_stage_status.py`
- Test: `tests/test_pipeline_state_machine.py`, `tests/test_pipeline_run_stage.py`

**Interfaces:**
- Consumes: 없음 (첫 Task)
- Produces:
  - `StageStatus.QUEUED == "QUEUED"`
  - `queries.queue_stage(conn, id, status, updated_at, updated_by) -> Record | None`
  - `queries.claim_stage_run(conn, id, status, started_at, updated_at, updated_by) -> Record | None` (조건이 `status = 'QUEUED'`로 바뀜)
  - `queries.find_stage_by_id(conn, id) -> Record | None`
  - `queries.fail_running_stages(conn, error, finished_at, updated_at)` — aiosql `!` 연산자라 asyncpg는 `"UPDATE 3"` 같은 **상태 문자열**을 돌려준다. 계수가 아니므로 반환값을 쓰지 않는다.
  - `queries.list_queued_stage_ids(conn) -> AsyncIterator[Record]`

- [ ] **Step 1: 실패하는 테스트를 쓴다**

`tests/test_pipeline_state_machine.py`에 아래를 추가한다.

```python
def test_pending_goes_to_queued_not_running():
    # 실행 요청은 곧바로 RUNNING이 아니라 QUEUED로 간다 — 워커가 집기 전 구간을
    # UI가 구분할 수 있어야 하고, [실행] 버튼이 두 번 눌리면 안 된다.
    assert pipeline.can_transition(StageStatus.PENDING, StageStatus.QUEUED)
    assert not pipeline.can_transition(StageStatus.PENDING, StageStatus.RUNNING)


def test_queued_goes_to_running_or_failed():
    assert pipeline.can_transition(StageStatus.QUEUED, StageStatus.RUNNING)
    # 기동 복구 경로: 앱이 죽어 남은 작업을 정리한다.
    assert pipeline.can_transition(StageStatus.QUEUED, StageStatus.FAILED)


def test_failed_retries_straight_into_queue():
    assert pipeline.can_transition(StageStatus.FAILED, StageStatus.QUEUED)
    assert not pipeline.can_transition(StageStatus.FAILED, StageStatus.PENDING)
```

`tests/test_pipeline_run_stage.py`에 아래를 추가한다.

```python
@pytest.mark.asyncio
async def test_queue_stage_is_idempotent_under_race(db_session):
    # 같은 단계에 실행 요청이 두 번 들어와도 두 번째는 0행 CAS로 거절돼야 한다.
    actor, project, stage = await _seed_project_and_stage(db_session)
    assert await pipeline.queue_stage(db_session, stage["id"], actor_id=actor) is True
    assert await pipeline.queue_stage(db_session, stage["id"], actor_id=actor) is False


@pytest.mark.asyncio
async def test_claim_stage_requires_queued(db_session):
    # PENDING을 워커가 곧바로 집으면 안 된다 — 반드시 QUEUED를 거친다.
    actor, project, stage = await _seed_project_and_stage(db_session)
    assert await pipeline.claim_stage(db_session, stage["id"], actor_id=actor) is None
    await pipeline.queue_stage(db_session, stage["id"], actor_id=actor)
    claimed = await pipeline.claim_stage(db_session, stage["id"], actor_id=actor)
    assert claimed is not None
    assert claimed["status"] == StageStatus.RUNNING
```

- [ ] **Step 2: 테스트를 돌려 실패를 확인한다**

Run: `uv run pytest tests/test_pipeline_state_machine.py tests/test_pipeline_run_stage.py -v`
Expected: FAIL — `AttributeError: QUEUED` 및 `module 'app.core.pipeline' has no attribute 'queue_stage'`

- [ ] **Step 3: `StageStatus.QUEUED`를 추가한다**

`app/constants.py`의 `StageStatus`를 다음으로 바꾼다.

```python
class StageStatus(StrEnum):
    """stages.status 코드값. DB에 대문자로 저장된다."""

    PENDING = "PENDING"
    QUEUED = "QUEUED"  # 실행 요청됨 — 워커가 아직 집지 않은 상태
    RUNNING = "RUNNING"
    NEEDS_REVIEW = "NEEDS_REVIEW"
    APPROVED = "APPROVED"
    FAILED = "FAILED"
```

`app/models/stage.py`의 `status` 필드 코멘트도 맞춘다.

```python
    status: str = Field(
        default=StageStatus.PENDING,
        sa_column_kwargs={
            "comment": "상태: PENDING|QUEUED|RUNNING|NEEDS_REVIEW|APPROVED|FAILED"
        },
    )
```

- [ ] **Step 4: SQL 쿼리를 고친다**

`app/queries/stages.sql`의 `claim_stage_run`을 아래 5개 쿼리로 교체/추가한다.

```sql
-- name: find_stage_by_id^
SELECT id, project_id, name, provider, status, output, error, attempt,
       started_at, finished_at, created_at, updated_at
FROM stages
WHERE id = :id;

-- name: queue_stage<!
-- PENDING/FAILED일 때만 QUEUED로 선점한다. 영향 행이 0이면(RETURNING 없음) 이미 큐에
-- 들어갔거나 실행 가능한 상태가 아니라는 뜻 — 중복 실행 요청 가드.
-- 재시도로 다시 큐에 들어가는 것이므로 지난 실패 메시지는 지운다.
UPDATE stages
SET status = :status,
    error = NULL,
    updated_at = :updated_at,
    updated_by = :updated_by
WHERE id = :id AND status IN ('PENDING', 'FAILED')
RETURNING id;

-- name: claim_stage_run<!
-- QUEUED일 때만 RUNNING으로 선점한다. 큐에 같은 stage_id가 두 번 들어가도 두 번째
-- claim은 0행을 반환하고 조용히 버려진다 — 워커 동시성 가드.
UPDATE stages
SET status = :status,
    started_at = :started_at,
    updated_at = :updated_at,
    updated_by = :updated_by
WHERE id = :id AND status = 'QUEUED'
RETURNING id;

-- name: fail_running_stages!
-- 앱이 죽으면서 RUNNING으로 남은 고아를 기동 시 정리한다. 중간 산출물 상태를 알 수
-- 없으므로 되살리지 않고 실패로 확정한다 — 사용자가 재시도할 수 있다.
-- updated_by는 사람 행위자가 없으므로 건드리지 않는다.
UPDATE stages
SET status = 'FAILED',
    error = :error,
    finished_at = :finished_at,
    updated_at = :updated_at
WHERE status = 'RUNNING';

-- name: list_queued_stage_ids
-- 기동 시 큐에 다시 넣을 대상. QUEUED는 아직 시작 전이므로 재투입이 안전하다.
SELECT id FROM stages WHERE status = 'QUEUED' ORDER BY id ASC;
```

- [ ] **Step 5: 상태 전이표와 primitive를 고친다**

`app/core/pipeline.py`의 `ALLOWED_TRANSITIONS`를 교체한다.

```python
# Stage.status 허용 전이. 여기 없는 전이는 모두 금지(잘못된 요청 → 409).
ALLOWED_TRANSITIONS: dict[str, set[str]] = {
    StageStatus.PENDING: {StageStatus.QUEUED},              # 실행 요청 → 큐
    StageStatus.QUEUED: {StageStatus.RUNNING, StageStatus.FAILED},  # FAILED는 기동 복구
    StageStatus.RUNNING: {StageStatus.NEEDS_REVIEW, StageStatus.FAILED},
    StageStatus.NEEDS_REVIEW: {StageStatus.APPROVED, StageStatus.PENDING},  # 승인 / 재생성
    StageStatus.FAILED: {StageStatus.QUEUED},               # 재시도는 곧바로 큐로
    StageStatus.APPROVED: set(),                            # 이 슬라이스의 종착
}
```

같은 파일의 `run_stage`(84~126행)를 아래 세 함수로 교체한다. `run_stage`는 API가 아직 동기 실행에 의존하므로 **조합 함수로 남겨 둔다 — Task 7에서 삭제한다.**

```python
async def queue_stage(session, stage_id: int, actor_id: int | None) -> bool:
    """PENDING/FAILED → QUEUED. 선점에 성공하면 True. 커밋은 호출자 몫."""
    conn = await raw_connection(session)
    claimed = await queries.queue_stage(
        conn, id=stage_id, status=StageStatus.QUEUED,
        updated_at=now_local(), updated_by=actor_id,
    )
    return claimed is not None


async def claim_stage(session, stage_id: int, actor_id: int | None) -> dict | None:
    """QUEUED → RUNNING. 경합에서 지면 None. 커밋은 호출자 몫."""
    conn = await raw_connection(session)
    claimed = await queries.claim_stage_run(
        conn, id=stage_id, status=StageStatus.RUNNING,
        started_at=now_local(), updated_at=now_local(), updated_by=actor_id,
    )
    if claimed is None:
        return None
    return decode_stage(await queries.find_stage_by_id(conn, id=stage_id))


async def run_claimed_stage(session, project: dict, stage: dict, actor_id: int) -> dict:
    """이미 RUNNING으로 선점된 단계의 provider를 실행하고 결과를 반영한다."""
    conn = await raw_connection(session)
    started = stage["started_at"]
    inputs, input_assets = await _previous_context(conn, project["id"], stage["name"])
    ctx = StageContext(
        topic=project["topic"],
        settings=project.get("settings", {}),
        inputs=inputs,
        input_assets=input_assets,
        attempt=stage["attempt"],
        workdir=f"projects/{project['id']}/{stage['name']}",
    )
    try:
        provider = get_provider(stage["name"], stage["provider"])   # 잘못된 provider 이름도 FAILED로 흡수
        provider.validate(ctx.settings)          # 키 누락 등 조기 실패 → FAILED로 흡수
        result = await provider.run(ctx)
        await _replace_assets(conn, stage["id"], result.assets, actor_id)
        status, output, error = StageStatus.NEEDS_REVIEW, result.output, None
    except AppError as exc:  # validate 실패·PROVIDER_NOT_FOUND 등 친절 메시지 그대로
        status, output, error = StageStatus.FAILED, {}, exc.message
    except Exception:  # 외부 SDK 오류(429/5xx/파싱 등)는 원문 대신 일반 안내 + 로그
        logger.exception("stage run failed: project=%s stage=%s", project["id"], stage["name"])
        status, output, error = StageStatus.FAILED, {}, "실행 중 오류가 발생했습니다. 잠시 후 다시 시도해 주세요."

    await queries.update_stage_run(
        conn, id=stage["id"], status=status, output=json.dumps(output), error=error,
        attempt=stage["attempt"], started_at=started, finished_at=now_local(),
        updated_at=now_local(), updated_by=actor_id,
    )
    await session.commit()
    updated = await queries.find_stage(conn, project_id=project["id"], name=stage["name"])
    return decode_stage(updated)


async def run_stage(session, project: dict, stage: dict, actor_id: int) -> dict:
    """[임시] 요청 안에서 큐 등록·선점·실행을 한 번에 한다.

    Task 7에서 API가 워커로 옮겨가면 삭제된다. 그때까지 기존 동작을 유지한다.
    """
    if not await queue_stage(session, stage["id"], actor_id):
        raise AppError(409, "STAGE_CONFLICT", "이미 실행 중이거나 검토 단계입니다.")
    claimed = await claim_stage(session, stage["id"], actor_id)
    if claimed is None:
        raise AppError(409, "STAGE_CONFLICT", "이미 실행 중이거나 검토 단계입니다.")
    return await run_claimed_stage(session, project, claimed, actor_id)
```

`regenerate_stage`의 마지막 두 줄을 아래로 바꾼다 (`reloaded`가 이제 `PENDING`이므로 `run_stage`가 다시 큐를 태운다).

```python
    reloaded = decode_stage(await queries.find_stage(conn, project_id=project["id"], name=stage["name"]))
    return await run_stage(session, project, reloaded, actor_id=actor_id)
```

> 이 줄은 원래와 같다. 확인만 하고 넘어간다.

- [ ] **Step 6: 마이그레이션을 만든다**

Run: `uv run alembic revision -m "add queued stage status"`

생성된 파일의 `upgrade`/`downgrade`를 아래로 채운다 (`revision`/`down_revision`은 생성된 값을 그대로 둔다).

```python
def upgrade() -> None:
    """Upgrade schema."""
    op.alter_column(
        "stages",
        "status",
        comment="상태: PENDING|QUEUED|RUNNING|NEEDS_REVIEW|APPROVED|FAILED",
        existing_type=sa.VARCHAR(),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.alter_column(
        "stages",
        "status",
        comment="상태: PENDING|RUNNING|NEEDS_REVIEW|APPROVED|FAILED",
        existing_type=sa.VARCHAR(),
    )
```

- [ ] **Step 7: 테스트를 돌려 통과를 확인한다**

Run: `uv run pytest tests/test_pipeline_state_machine.py tests/test_pipeline_run_stage.py tests/test_pipeline_transition.py tests/test_api_projects.py tests/test_alembic_migration.py -v`
Expected: PASS (전부). 실패하면 `run_stage` 조합 함수가 기존 동작을 그대로 재현하는지 먼저 확인한다.

- [ ] **Step 8: 커밋**

```bash
git add app/constants.py app/models/stage.py app/queries/stages.sql app/core/pipeline.py alembic/versions tests/test_pipeline_state_machine.py tests/test_pipeline_run_stage.py
git commit -m "기능: QUEUED 단계 상태와 두 단계 CAS(queue_stage/claim_stage) 도입"
```

---

## Task 2: 인메모리 이벤트 버스 `app/core/events.py`

**Files:**
- Create: `app/core/events.py`
- Modify: `tests/conftest.py`
- Test: `tests/test_core_events.py`

**Interfaces:**
- Consumes: 없음
- Produces:
  - `events.publish(project_id: int, event: dict) -> None`
  - `events.subscribe(project_id: int)` — `async with` 컨텍스트, `asyncio.Queue`를 내준다
  - `events.set_progress(stage_id: int, payload: dict) -> None`
  - `events.get_progress(stage_id: int) -> dict | None`
  - `events.clear_progress(stage_id: int) -> None`
  - `events.reset() -> None` (테스트 전용)

- [ ] **Step 1: 실패하는 테스트를 쓴다**

`tests/test_core_events.py`를 만든다.

```python
import asyncio

from app.core import events

PROJECT_ID = 7


async def test_publish_reaches_every_subscriber():
    async with events.subscribe(PROJECT_ID) as a, events.subscribe(PROJECT_ID) as b:
        events.publish(PROJECT_ID, {"type": "stage"})
        assert a.get_nowait() == {"type": "stage"}
        assert b.get_nowait() == {"type": "stage"}


async def test_publish_ignores_other_projects():
    async with events.subscribe(PROJECT_ID) as queue:
        events.publish(PROJECT_ID + 1, {"type": "stage"})
        assert queue.empty()


async def test_unsubscribe_on_exit():
    async with events.subscribe(PROJECT_ID):
        pass
    # 구독자가 사라지면 발행이 아무 데도 쌓이지 않는다(누수 없음).
    events.publish(PROJECT_ID, {"type": "stage"})
    assert events._subscribers == {}


async def test_full_queue_drops_oldest_and_keeps_newest():
    # 느린 구독자 하나가 워커를 멈춰세우면 안 된다. 진행률은 최신값만 의미가 있다.
    async with events.subscribe(PROJECT_ID) as queue:
        for i in range(events._QUEUE_MAX + 5):
            events.publish(PROJECT_ID, {"type": "progress", "n": i})
        drained = []
        while not queue.empty():
            drained.append(queue.get_nowait())
    assert len(drained) == events._QUEUE_MAX
    assert drained[-1] == {"type": "progress", "n": events._QUEUE_MAX + 4}


async def test_progress_cache_roundtrip():
    assert events.get_progress(11) is None
    events.set_progress(11, {"percent": 40.0, "message": "받아쓰는 중…"})
    assert events.get_progress(11)["percent"] == 40.0
    events.clear_progress(11)
    assert events.get_progress(11) is None


async def test_publish_never_raises():
    # 발행 실패가 파이프라인을 죽이면 안 된다.
    class Exploding(asyncio.Queue):
        def put_nowait(self, item):
            raise RuntimeError("boom")

    events._subscribers.setdefault(PROJECT_ID, set()).add(Exploding())
    events.publish(PROJECT_ID, {"type": "stage"})  # 예외가 새어 나오면 실패
```

- [ ] **Step 2: 테스트를 돌려 실패를 확인한다**

Run: `uv run pytest tests/test_core_events.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.core.events'`

- [ ] **Step 3: `app/core/events.py`를 만든다**

```python
import asyncio
import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

logger = logging.getLogger(__name__)

# 구독자 한 명이 밀리더라도 워커를 멈춰세우지 않도록 큐 길이를 묶는다.
_QUEUE_MAX = 100

_subscribers: dict[int, set[asyncio.Queue]] = {}
_last_progress: dict[int, dict] = {}


def publish(project_id: int, event: dict) -> None:
    """이 프로젝트를 보고 있는 구독자들에게 이벤트를 흘린다.

    절대 await하지 않고 예외도 밖으로 내보내지 않는다 — 이벤트 발행 실패가
    단계 실행을 죽이면 안 된다.
    """
    for queue in list(_subscribers.get(project_id, ())):
        try:
            queue.put_nowait(event)
        except asyncio.QueueFull:
            # 가장 오래된 것을 버리고 최신 이벤트를 넣는다. 진행률은 최신값만 의미가 있다.
            try:
                queue.get_nowait()
                queue.put_nowait(event)
            except (asyncio.QueueEmpty, asyncio.QueueFull):
                logger.warning("구독자 큐를 비우지 못했습니다: project=%s", project_id)
        except Exception:
            logger.exception("이벤트 발행 실패: project=%s", project_id)


@asynccontextmanager
async def subscribe(project_id: int) -> AsyncIterator[asyncio.Queue]:
    """이 프로젝트의 이벤트를 받을 큐를 등록한다. 블록을 벗어나면 반드시 해제된다."""
    queue: asyncio.Queue = asyncio.Queue(maxsize=_QUEUE_MAX)
    _subscribers.setdefault(project_id, set()).add(queue)
    try:
        yield queue
    finally:
        remaining = _subscribers.get(project_id)
        if remaining is not None:
            remaining.discard(queue)
            if not remaining:
                _subscribers.pop(project_id, None)


def set_progress(stage_id: int, payload: dict) -> None:
    """마지막 진행률을 기억한다. 뒤늦게 접속한 구독자의 스냅샷에 실린다(DB엔 남기지 않는다)."""
    _last_progress[stage_id] = payload


def get_progress(stage_id: int) -> dict | None:
    return _last_progress.get(stage_id)


def clear_progress(stage_id: int) -> None:
    _last_progress.pop(stage_id, None)


def reset() -> None:
    """테스트 전용 — 프로세스 전역 상태를 비운다."""
    _subscribers.clear()
    _last_progress.clear()
```

- [ ] **Step 4: 테스트 간 전역 상태를 격리한다**

`tests/conftest.py` 맨 끝에 아래를 추가한다.

```python
@pytest.fixture(autouse=True)
def reset_events():
    # 이벤트 버스는 프로세스 전역이라 테스트끼리 샌다. 앞뒤로 비운다.
    from app.core import events

    events.reset()
    yield
    events.reset()
```

- [ ] **Step 5: 테스트를 돌려 통과를 확인한다**

Run: `uv run pytest tests/test_core_events.py -v`
Expected: PASS (6 passed)

- [ ] **Step 6: 커밋**

```bash
git add app/core/events.py tests/test_core_events.py tests/conftest.py
git commit -m "기능: 인메모리 이벤트 버스(core/events) 추가"
```

---

## Task 3: 공개 표현 추출 `app/core/views.py`

API 응답과 SSE 이벤트가 같은 모양을 써야 한다. 지금은 `app/api/projects.py`의 비공개 함수라 워커가 쓸 수 없고, `core`가 `api`를 import하면 의존 방향이 뒤집힌다. `core`로 끌어내린다.

**Files:**
- Create: `app/core/views.py`
- Modify: `app/api/projects.py:21-64`
- Test: `tests/test_core_views.py`

**Interfaces:**
- Consumes: `pipeline.decode_stage`, `queries.*` (Task 1)
- Produces:
  - `views.project_public(project: dict) -> dict`
  - `views.stage_public(stage: dict) -> dict`
  - `views.detail(conn, project_id: int) -> dict` — `{"project": ..., "stages": [...]}`
  - `views.stage_event(project: dict, stage: dict) -> dict` — `{"type": "stage", "project": ..., "stage": ...}`
  - `views.progress_event(stage_name: str, percent: float | None, message: str) -> dict` — `{"type": "progress", "stage": ..., "percent": ..., "message": ...}`

- [ ] **Step 1: 실패하는 테스트를 쓴다**

`tests/test_core_views.py`를 만든다.

```python
from app.core import views


def test_stage_event_shape():
    project = {"id": 1, "title": "t", "topic": "주제", "status": "REVIEW",
               "current_stage": "voice", "created_at": None}
    stage = {"id": 9, "name": "voice", "provider": "fake", "status": "RUNNING",
             "output": {}, "error": None, "attempt": 0}
    event = views.stage_event(project, stage)
    assert event["type"] == "stage"
    assert event["project"]["current_stage"] == "voice"
    assert event["stage"]["status"] == "RUNNING"
    # 소유자 id 같은 내부 필드가 새어 나가면 안 된다.
    assert "owner_id" not in event["project"]


def test_progress_event_allows_null_percent():
    # script·voice는 진짜 %가 없다 — null을 그대로 실어 보낸다.
    event = views.progress_event("script", None, "대본을 생성하는 중…")
    assert event == {"type": "progress", "stage": "script",
                     "percent": None, "message": "대본을 생성하는 중…"}
```

- [ ] **Step 2: 테스트를 돌려 실패를 확인한다**

Run: `uv run pytest tests/test_core_views.py -v`
Expected: FAIL — `ImportError: cannot import name 'views' from 'app.core'`

- [ ] **Step 3: `app/core/views.py`를 만든다**

`app/api/projects.py`의 `_project_public` · `_stage_public` · `_detail` 본문을 그대로 옮긴다.

```python
"""API 응답과 SSE 이벤트가 함께 쓰는 공개 표현(shape).

api에 두면 워커가 쓸 수 없고 core→api 역방향 의존이 생긴다. core에 둔다.
"""

from app.core.pipeline import decode_stage
from app.queries import queries


def project_public(project: dict) -> dict:
    return {
        "id": project["id"],
        "title": project["title"],
        "topic": project["topic"],
        "status": project["status"],
        "current_stage": project["current_stage"],
        "created_at": project["created_at"].isoformat() if project.get("created_at") else None,
    }


def stage_public(stage: dict) -> dict:
    return {
        "id": stage["id"],
        "name": stage["name"],
        "provider": stage["provider"],
        "status": stage["status"],
        "output": stage["output"],
        "error": stage["error"],
        "attempt": stage["attempt"],
    }


async def detail(conn, project_id: int) -> dict:
    project = decode_stage(await queries.find_project_by_id(conn, id=project_id))
    stages = [
        stage_public(decode_stage(dict(r)))
        async for r in queries.list_stages_by_project(conn, project_id=project_id)
    ]
    return {"project": project_public(project), "stages": stages}


def stage_event(project: dict, stage: dict) -> dict:
    """단계 상태가 바뀌었다. 프로젝트 status/current_stage도 함께 실어 한 번에 갱신시킨다."""
    return {
        "type": "stage",
        "project": project_public(project),
        "stage": stage_public(stage),
    }


def progress_event(stage_name: str, percent: float | None, message: str) -> dict:
    """percent가 None이면 진짜 진행률이 없다는 뜻 — UI는 불확정 바를 보여준다."""
    return {
        "type": "progress",
        "stage": stage_name,
        "percent": percent,
        "message": message,
    }
```

- [ ] **Step 4: `app/api/projects.py`가 이것을 쓰게 한다**

21~64행의 `_project_public` · `_stage_public` · `_detail` 정의를 지우고, import와 호출부를 바꾼다.

```python
from app.core import views
```

- `_load_owned_project`와 `_load_stage`는 그대로 둔다 (API 전용 인가 로직).
- 파일 안의 `_detail(conn, project_id)` 호출을 전부 `views.detail(conn, project_id)`로 바꾼다 (`create_project`, `get_project`, `run_stage`, `approve_stage`, `regenerate_stage` — 5곳).
- `list_projects`는 `_detail`이 아니라 `_project_public`을 직접 부른다. 정의를 지웠으므로 이 1곳도 `views.project_public`으로 바꿔야 `NameError`가 안 난다.

- [ ] **Step 5: 테스트를 돌려 통과를 확인한다**

Run: `uv run pytest tests/test_core_views.py tests/test_api_projects.py tests/test_api_asset.py -v`
Expected: PASS (전부). API 응답 모양이 바뀌지 않았으므로 기존 테스트가 그대로 통과해야 한다.

- [ ] **Step 6: 커밋**

```bash
git add app/core/views.py app/api/projects.py tests/test_core_views.py
git commit -m "리팩터: API 응답 표현을 core/views로 내려 워커·SSE와 공유"
```

---

## Task 4: `StageContext.on_progress` 계약

**Files:**
- Modify: `app/providers/base.py:7-16`
- Modify: `app/core/pipeline.py` (`run_claimed_stage` 시그니처)
- Test: `tests/test_provider_base.py`

**Interfaces:**
- Consumes: `views.progress_event` (Task 3)
- Produces:
  - `StageContext.on_progress: Callable[[float | None, str], None]` — 기본값은 아무것도 하지 않는 `noop_progress`
  - `pipeline.run_claimed_stage(session, project, stage, actor_id, on_progress=noop_progress) -> dict`

- [ ] **Step 1: 실패하는 테스트를 쓴다**

`tests/test_provider_base.py`에 추가한다.

```python
def test_stage_context_progress_defaults_to_noop():
    # provider가 진행률을 안 내도 그냥 돌아야 한다 — 계약은 선택적이다.
    ctx = StageContext(topic="주제")
    ctx.on_progress(None, "무시된다")  # 예외가 나면 실패


def test_stage_context_accepts_progress_callback():
    seen = []
    ctx = StageContext(topic="주제", on_progress=lambda p, m: seen.append((p, m)))
    ctx.on_progress(42.0, "받아쓰는 중…")
    assert seen == [(42.0, "받아쓰는 중…")]
```

- [ ] **Step 2: 테스트를 돌려 실패를 확인한다**

Run: `uv run pytest tests/test_provider_base.py -v`
Expected: FAIL — `AttributeError: 'StageContext' object has no attribute 'on_progress'`

- [ ] **Step 3: 계약을 추가한다**

`app/providers/base.py`의 상단을 다음으로 바꾼다.

```python
from abc import ABC, abstractmethod
from collections.abc import Callable
from dataclasses import dataclass, field

from app.utils.errors import AppError


def noop_progress(percent: float | None, message: str) -> None:
    """기본 진행률 콜백. provider가 진행률을 안 내도 그냥 돌게 한다."""


@dataclass
class StageContext:
    """단계 실행에 필요한 입력."""

    topic: str
    settings: dict = field(default_factory=dict)
    inputs: dict = field(default_factory=dict)  # 이전 단계 산출물 (script엔 비어있음)
    input_assets: dict = field(default_factory=dict)  # {단계이름: [{kind, path, meta}]} 파일 산출물
    attempt: int = 0  # 재생성 횟수 → provider 출력 변주 seed
    workdir: str = ""  # 저장소 기준 이 단계의 디렉토리 (파일을 만드는 단계만 사용)
    # 진행 상황 보고. percent가 None이면 진짜 진행률이 없다는 뜻(메시지만 쓴다).
    # 워커 스레드에서 호출될 수 있으므로 구현은 스레드 안전해야 한다.
    on_progress: Callable[[float | None, str], None] = noop_progress
```

- [ ] **Step 4: `run_claimed_stage`가 콜백을 넘기게 한다**

`app/core/pipeline.py`에서 import를 넓히고 시그니처와 `ctx` 생성을 바꾼다.

```python
from app.providers.base import StageContext, get_provider, noop_progress
```

```python
async def run_claimed_stage(
    session, project: dict, stage: dict, actor_id: int, on_progress=noop_progress
) -> dict:
```

```python
    ctx = StageContext(
        topic=project["topic"],
        settings=project.get("settings", {}),
        inputs=inputs,
        input_assets=input_assets,
        attempt=stage["attempt"],
        workdir=f"projects/{project['id']}/{stage['name']}",
        on_progress=on_progress,
    )
```

- [ ] **Step 5: 테스트를 돌려 통과를 확인한다**

Run: `uv run pytest tests/test_provider_base.py tests/test_pipeline_run_stage.py -v`
Expected: PASS

- [ ] **Step 6: 커밋**

```bash
git add app/providers/base.py app/core/pipeline.py tests/test_provider_base.py
git commit -m "기능: StageContext.on_progress 진행률 보고 계약 추가"
```

---

## Task 5: `StageWorker` — 큐·워커 루프·기동 복구

**Files:**
- Create: `app/core/worker.py`
- Modify: `app/config.py`
- Test: `tests/test_core_worker.py`, `tests/test_config.py`

**Interfaces:**
- Consumes: `pipeline.queue_stage` · `pipeline.claim_stage` · `pipeline.run_claimed_stage` (Task 1·4), `events.*` (Task 2), `views.stage_event` · `views.progress_event` (Task 3)
- Produces:
  - `worker.StageWorker(session_factory=None, concurrency=None)`
  - `StageWorker.enqueue(stage_id: int) -> None`
  - `await StageWorker.run_one(stage_id: int) -> None`
  - `await StageWorker.start() -> None` / `await StageWorker.stop() -> None`
  - `worker.get_worker() -> StageWorker` — 앱 전역 싱글턴
  - `settings.worker_concurrency: int = 1`

- [ ] **Step 1: 실패하는 테스트를 쓴다**

`tests/test_core_worker.py`를 만든다.

```python
import json
from contextlib import asynccontextmanager

import pytest

from app.auth.security import hash_password
from app.constants import ProjectStatus, StageName, StageStatus, UserRole, UserStatus
from app.core import events, pipeline
from app.core.worker import StageWorker
from app.db import raw_connection
from app.models.user import User
from app.queries import queries
from app.utils.time import now_local


def _factory(session):
    """워커가 자체 세션 대신 테스트 세션을 쓰게 한다 — SAVEPOINT 격리 유지."""

    @asynccontextmanager
    async def _make():
        yield session

    return _make


async def _seed(session, email: str, *, status=StageStatus.PENDING, settings: dict | None = None):
    conn = await raw_connection(session)
    now = now_local()
    user = User(email=email, password_hash=hash_password("pw12345"),
                role=UserRole.MEMBER, status=UserStatus.ACTIVE)
    session.add(user)
    await session.commit()
    await session.refresh(user)

    project_id = await queries.insert_project(
        conn, owner_id=user.id, title="t", topic="바다 거북",
        status=ProjectStatus.DRAFT, current_stage=StageName.SCRIPT,
        settings=json.dumps(settings or {}),
        created_at=now, updated_at=now, created_by=user.id, updated_by=user.id,
    )
    stage_id = await queries.insert_stage(
        conn, project_id=project_id, name=StageName.SCRIPT, provider="fake",
        status=status, output=json.dumps({}), error=None, attempt=0,
        started_at=None, finished_at=None,
        created_at=now, updated_at=now, created_by=user.id, updated_by=user.id,
    )
    await session.commit()
    return user.id, project_id, stage_id


async def test_run_one_executes_queued_stage(db_session):
    _, project_id, stage_id = await _seed(db_session, "w1@example.com")
    await pipeline.queue_stage(db_session, stage_id, actor_id=None)
    await db_session.commit()

    worker = StageWorker(session_factory=_factory(db_session))
    await worker.run_one(stage_id)

    conn = await raw_connection(db_session)
    stage = dict(await queries.find_stage_by_id(conn, id=stage_id))
    assert stage["status"] == StageStatus.NEEDS_REVIEW


async def test_run_one_publishes_running_then_final(db_session):
    _, project_id, stage_id = await _seed(db_session, "w2@example.com")
    await pipeline.queue_stage(db_session, stage_id, actor_id=None)
    await db_session.commit()

    worker = StageWorker(session_factory=_factory(db_session))
    async with events.subscribe(project_id) as queue:
        await worker.run_one(stage_id)
        received = []
        while not queue.empty():
            received.append(queue.get_nowait())

    statuses = [e["stage"]["status"] for e in received if e["type"] == "stage"]
    assert statuses == [StageStatus.RUNNING, StageStatus.NEEDS_REVIEW]


async def test_run_one_ignores_stage_not_queued(db_session):
    # 큐에 같은 id가 두 번 들어가도 두 번째는 조용히 버려진다.
    _, _, stage_id = await _seed(db_session, "w3@example.com")
    worker = StageWorker(session_factory=_factory(db_session))
    await worker.run_one(stage_id)  # PENDING이므로 claim 실패

    conn = await raw_connection(db_session)
    assert dict(await queries.find_stage_by_id(conn, id=stage_id))["status"] == StageStatus.PENDING


async def test_run_one_marks_failed_on_provider_error(db_session, monkeypatch):
    _, _, stage_id = await _seed(db_session, "w4@example.com")
    await pipeline.queue_stage(db_session, stage_id, actor_id=None)
    await db_session.commit()

    async def _boom(self, ctx):
        raise RuntimeError("provider 폭발")

    monkeypatch.setattr("app.providers.script.fake.FakeScript.run", _boom)

    worker = StageWorker(session_factory=_factory(db_session))
    await worker.run_one(stage_id)

    conn = await raw_connection(db_session)
    stage = dict(await queries.find_stage_by_id(conn, id=stage_id))
    assert stage["status"] == StageStatus.FAILED
    assert stage["error"]


async def test_recover_fails_orphaned_running_and_requeues_queued(db_session):
    _, _, running_id = await _seed(db_session, "w5@example.com", status=StageStatus.RUNNING)
    _, _, queued_id = await _seed(db_session, "w6@example.com", status=StageStatus.QUEUED)

    worker = StageWorker(session_factory=_factory(db_session))
    await worker._recover()

    conn = await raw_connection(db_session)
    orphan = dict(await queries.find_stage_by_id(conn, id=running_id))
    assert orphan["status"] == StageStatus.FAILED
    assert "재시작" in orphan["error"]
    assert worker._queue.get_nowait() == queued_id
```

- [ ] **Step 2: 테스트를 돌려 실패를 확인한다**

Run: `uv run pytest tests/test_core_worker.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.core.worker'`

- [ ] **Step 3: 설정을 추가한다**

`app/config.py`의 `Settings`에 한 줄 추가한다.

```python
    # whisper·ffmpeg는 CPU를 포화시킨다. 병렬로 돌려도 서로 느려지기만 하므로 기본 1.
    worker_concurrency: int = 1
```

`tests/test_config.py`에 추가한다.

```python
def test_worker_concurrency_defaults_to_one():
    assert get_settings().worker_concurrency == 1
```

- [ ] **Step 4: `app/core/worker.py`를 만든다**

```python
import asyncio
import logging

from app.config import get_settings
from app.constants import StageStatus
from app.core import events, pipeline, views
from app.db import async_session_maker, raw_connection
from app.queries import queries
from app.utils.time import now_local

logger = logging.getLogger(__name__)

# 종료 시 진행 중인 단계를 이만큼 기다린 뒤 취소한다.
_SHUTDOWN_GRACE_SEC = 5.0
_RESTART_ERROR = "서버가 재시작되어 중단되었습니다. 다시 실행해 주세요."


class StageWorker:
    """stages 테이블을 큐로 삼아 단계를 백그라운드에서 실행한다.

    session_factory를 주입받는 이유: 워커가 async_session_maker를 직접 잡으면
    테스트의 SAVEPOINT 격리 밖으로 나가 테스트 데이터를 못 보고 실제 DB에 쓴다.
    """

    def __init__(self, session_factory=None, concurrency: int | None = None):
        self._session_factory = session_factory or async_session_maker
        self._concurrency = concurrency or get_settings().worker_concurrency
        self._queue: asyncio.Queue[int] = asyncio.Queue()
        self._tasks: list[asyncio.Task] = []

    def enqueue(self, stage_id: int) -> None:
        """실행 대기열에 넣는다. 상태 선점(QUEUED)은 호출자가 이미 끝냈다고 본다."""
        self._queue.put_nowait(stage_id)

    async def start(self) -> None:
        await self._recover()
        self._tasks = [
            asyncio.create_task(self._loop(), name=f"stage-worker-{i}")
            for i in range(self._concurrency)
        ]

    async def stop(self) -> None:
        if not self._tasks:
            return
        try:
            await asyncio.wait_for(self._queue.join(), timeout=_SHUTDOWN_GRACE_SEC)
        except TimeoutError:
            logger.warning("%.0f초 안에 끝나지 않은 단계가 있어 취소합니다.", _SHUTDOWN_GRACE_SEC)
        for task in self._tasks:
            task.cancel()
        await asyncio.gather(*self._tasks, return_exceptions=True)
        self._tasks = []

    async def _loop(self) -> None:
        while True:
            stage_id = await self._queue.get()
            try:
                await self.run_one(stage_id)
            except Exception:
                # 한 단계의 실패가 워커 루프를 죽이면 안 된다.
                logger.exception("단계 실행 중 처리되지 않은 예외: stage=%s", stage_id)
            finally:
                self._queue.task_done()

    async def _recover(self) -> None:
        """앱이 죽으면서 남은 고아 상태를 정리한다. 기동 시 1회."""
        async with self._session_factory() as session:
            conn = await raw_connection(session)
            now = now_local()
            # RUNNING은 중간 산출물 상태를 알 수 없다 — 되살리지 않고 실패로 확정한다.
            await queries.fail_running_stages(
                conn, error=_RESTART_ERROR, finished_at=now, updated_at=now
            )
            # QUEUED는 아직 시작 전이므로 그대로 다시 태운다.
            queued = [r["id"] async for r in queries.list_queued_stage_ids(conn)]
            await session.commit()
        for stage_id in queued:
            self.enqueue(stage_id)
        if queued:
            logger.info("기동 복구: 대기 중이던 단계 %d건을 다시 큐에 넣었습니다.", len(queued))

    async def run_one(self, stage_id: int) -> None:
        """한 단계를 선점해 실행하고 결과를 이벤트로 알린다."""
        async with self._session_factory() as session:
            conn = await raw_connection(session)
            row = await queries.find_stage_by_id(conn, id=stage_id)
            if row is None:
                return
            project = pipeline.decode_stage(
                await queries.find_project_by_id(conn, id=row["project_id"])
            )
            actor = project["owner_id"]

            stage = await pipeline.claim_stage(session, stage_id, actor_id=actor)
            if stage is None:
                return  # 경합에서 졌거나 QUEUED가 아니다 — 조용히 버린다
            await session.commit()  # 발행은 항상 커밋 이후
            events.publish(project["id"], views.stage_event(project, stage))

            on_progress = self._make_on_progress(project["id"], stage["id"], stage["name"])
            updated = await pipeline.run_claimed_stage(
                session, project, stage, actor_id=actor, on_progress=on_progress
            )
            events.clear_progress(stage["id"])
            project = pipeline.decode_stage(
                await queries.find_project_by_id(conn, id=project["id"])
            )
            events.publish(project["id"], views.stage_event(project, updated))

    def _make_on_progress(self, project_id: int, stage_id: int, stage_name: str):
        """진행률 콜백을 만든다.

        whisper·ffmpeg는 asyncio.to_thread 안에서 돌므로 콜백이 워커 스레드에서
        불린다. 이벤트 버스는 이벤트 루프 것이므로 루프로 넘겨서 만진다.
        """
        loop = asyncio.get_running_loop()

        def _apply(payload: dict) -> None:
            events.set_progress(stage_id, payload)
            events.publish(project_id, payload)

        def on_progress(percent: float | None, message: str) -> None:
            loop.call_soon_threadsafe(_apply, views.progress_event(stage_name, percent, message))

        return on_progress


_worker: StageWorker | None = None


def get_worker() -> StageWorker:
    """앱 전역 워커. lifespan이 start/stop을 부르고 API가 enqueue한다."""
    global _worker
    if _worker is None:
        _worker = StageWorker()
    return _worker
```

- [ ] **Step 5: 테스트를 돌려 통과를 확인한다**

Run: `uv run pytest tests/test_core_worker.py tests/test_config.py -v`
Expected: PASS

- [ ] **Step 6: 커밋**

```bash
git add app/core/worker.py app/config.py tests/test_core_worker.py tests/test_config.py
git commit -m "기능: 백그라운드 StageWorker(큐·기동 복구·이벤트 발행) 추가"
```

---

## Task 6: 자동 실행 모드 (`auto_run`)

**Files:**
- Modify: `app/core/pipeline.py` (`_next_stage` → `next_stage` 공개)
- Modify: `app/core/worker.py` (`run_one` 뒤에 연쇄)
- Test: `tests/test_core_worker.py`

**Interfaces:**
- Consumes: `pipeline.approve_stage` (기존), `StageWorker.run_one` (Task 5)
- Produces: `pipeline.next_stage(name: str) -> str | None` (기존 `_next_stage`의 공개 이름)

- [ ] **Step 1: 실패하는 테스트를 쓴다**

`tests/test_core_worker.py`에 추가한다.

```python
async def test_auto_run_approves_and_queues_next_stage(db_session):
    _, project_id, stage_id = await _seed(
        db_session, "auto1@example.com", settings={"auto_run": True}
    )
    await pipeline.queue_stage(db_session, stage_id, actor_id=None)
    await db_session.commit()

    worker = StageWorker(session_factory=_factory(db_session))
    await worker.run_one(stage_id)

    conn = await raw_connection(db_session)
    script = dict(await queries.find_stage_by_id(conn, id=stage_id))
    voice = dict(await queries.find_stage(conn, project_id=project_id, name=StageName.VOICE))
    assert script["status"] == StageStatus.APPROVED
    assert voice["status"] == StageStatus.QUEUED
    # 재귀가 아니라 큐를 경유해야 한다 — 스택이 쌓이면 안 된다.
    assert worker._queue.get_nowait() == voice["id"]


async def test_auto_run_stops_on_failure(db_session, monkeypatch):
    _, project_id, stage_id = await _seed(
        db_session, "auto2@example.com", settings={"auto_run": True}
    )
    await pipeline.queue_stage(db_session, stage_id, actor_id=None)
    await db_session.commit()

    async def _boom(self, ctx):
        raise RuntimeError("provider 폭발")

    monkeypatch.setattr("app.providers.script.fake.FakeScript.run", _boom)

    worker = StageWorker(session_factory=_factory(db_session))
    await worker.run_one(stage_id)

    conn = await raw_connection(db_session)
    assert dict(await queries.find_stage_by_id(conn, id=stage_id))["status"] == StageStatus.FAILED
    assert await queries.find_stage(conn, project_id=project_id, name=StageName.VOICE) is None
    assert worker._queue.empty()


async def test_manual_mode_does_not_chain(db_session):
    # auto_run이 없으면 승인은 사람이 한다.
    _, project_id, stage_id = await _seed(db_session, "manual@example.com")
    await pipeline.queue_stage(db_session, stage_id, actor_id=None)
    await db_session.commit()

    worker = StageWorker(session_factory=_factory(db_session))
    await worker.run_one(stage_id)

    conn = await raw_connection(db_session)
    assert dict(await queries.find_stage_by_id(conn, id=stage_id))["status"] == StageStatus.NEEDS_REVIEW
    assert worker._queue.empty()
```

- [ ] **Step 2: 테스트를 돌려 실패를 확인한다**

Run: `uv run pytest tests/test_core_worker.py -k auto_run -v`
Expected: FAIL — script가 `NEEDS_REVIEW`에 머물고 voice 단계가 없다

- [ ] **Step 3: `_next_stage`를 공개한다**

`app/core/pipeline.py`에서 이름을 바꾸고 호출부(`approve_stage` 안 1곳)도 함께 고친다.

```python
def next_stage(name: str) -> str | None:
    """STAGE_ORDER에서 다음 단계 이름. 마지막이면 None."""
    idx = STAGE_ORDER.index(name)
    return STAGE_ORDER[idx + 1] if idx + 1 < len(STAGE_ORDER) else None
```

```python
    nxt = next_stage(stage["name"])
```

- [ ] **Step 4: 워커에 연쇄를 붙인다**

`app/core/worker.py`의 `run_one` 마지막(`events.publish(... updated ...)`) 다음에 이어 붙인다.

```python
            await self._chain_if_auto(session, conn, project, updated, actor)
```

그리고 메서드를 추가한다.

```python
    async def _chain_if_auto(self, session, conn, project: dict, stage: dict, actor: int) -> None:
        """자동 진행 모드면 검토를 건너뛰고 다음 단계까지 밀어준다.

        승인은 기존 approve_stage 경로를 그대로 태운다 — 자동/수동이 같은 코드를
        지나므로 상태 머신에 새 규칙이 필요 없다. 실패하면 여기 오지 않고 멈춘다.
        """
        if stage["status"] != StageStatus.NEEDS_REVIEW:
            return
        if not project.get("settings", {}).get("auto_run"):
            return

        await pipeline.approve_stage(session, project, stage, actor_id=actor)
        # approve_stage가 내부에서 커밋했다 — 커밋은 커넥션을 풀에 돌려주므로 핸들을 다시 잡는다.
        conn = await raw_connection(session)
        approved = pipeline.decode_stage(await queries.find_stage_by_id(conn, id=stage["id"]))
        project = pipeline.decode_stage(await queries.find_project_by_id(conn, id=project["id"]))
        events.publish(project["id"], views.stage_event(project, approved))

        nxt = pipeline.next_stage(stage["name"])
        if nxt is None:
            return  # 마지막 단계 — approve_stage가 프로젝트를 DONE으로 만들었다
        nxt_row = await queries.find_stage(conn, project_id=project["id"], name=nxt)
        if nxt_row is None:
            return
        if not await pipeline.queue_stage(session, nxt_row["id"], actor_id=actor):
            return
        await session.commit()
        conn = await raw_connection(session)  # 커밋 이후 — 위와 같은 이유로 재획득
        queued = pipeline.decode_stage(await queries.find_stage_by_id(conn, id=nxt_row["id"]))
        events.publish(project["id"], views.stage_event(project, queued))
        # 재귀 호출이 아니라 큐를 경유한다 — 4단계를 돌아도 스택이 자라지 않는다.
        self.enqueue(nxt_row["id"])
```

- [ ] **Step 5: 테스트를 돌려 통과를 확인한다**

Run: `uv run pytest tests/test_core_worker.py tests/test_pipeline_transition.py -v`
Expected: PASS

- [ ] **Step 6: 커밋**

```bash
git add app/core/worker.py app/core/pipeline.py tests/test_core_worker.py
git commit -m "기능: 자동 진행 모드 — 성공 시 승인하고 다음 단계를 큐에 투입"
```

---

## Task 7: API 배선 — 202 · `auto_run` · lifespan

**Files:**
- Modify: `app/api/projects.py`
- Modify: `app/main.py`
- Modify: `app/core/pipeline.py` (임시 `run_stage` 삭제, `regenerate_stage` 변경)
- Test: `tests/test_api_projects.py`, `tests/test_pipeline_run_stage.py`
- Test (동기 실행을 전제하던 기존 테스트 — 함께 고쳐야 한다):
  - `tests/test_pipeline_validate.py`, `tests/test_pipeline_voice_run.py` — 삭제된 `pipeline.run_stage`를 호출한다. `queue_stage` → `claim_stage` → `run_claimed_stage` 조합으로 바꾼다.
  - `tests/test_api_captions.py`, `tests/test_api_render.py` — `POST /run` 응답에서 곧바로 산출물을 읽는다. 202를 받은 뒤 워커를 한 번 돌려(`_drain`) 완료시킨 다음 `GET /projects/{id}`로 결과를 읽도록 바꾼다.

**Interfaces:**
- Consumes: `worker.get_worker()` (Task 5), `views.detail` (Task 3), `pipeline.queue_stage` (Task 1)
- Produces:
  - `POST /api/projects` 본문에 `auto_run: bool = False`
  - `POST /api/projects/{id}/stages/{name}/run` → **202**
  - `POST /api/projects/{id}/stages/{name}/regenerate` → **202**
  - `pipeline.regenerate_stage(session, project, stage, actor_id) -> None` (실행하지 않고 큐까지만)

- [ ] **Step 1: 실패하는 테스트를 쓴다**

`tests/test_api_projects.py`의 `test_run_then_approve_flow` · `test_regenerate_increments_attempt` · `test_run_twice_conflicts`를 아래로 교체하고 나머지를 추가한다.

```python
async def test_run_returns_202_and_queues(client, db_session):
    # 실행은 이제 요청 안에서 끝나지 않는다 — 즉시 202 + QUEUED로 돌아온다.
    await _login(client, db_session, "b@example.com")
    pid = (await client.post("/api/projects", json={"title": "t", "topic": "우주"})).json()["project"]["id"]

    ran = await client.post(f"/api/projects/{pid}/stages/script/run")
    assert ran.status_code == 202
    assert ran.json()["stages"][0]["status"] == StageStatus.QUEUED


async def test_run_twice_conflicts(client, db_session):
    await _login(client, db_session, "d@example.com")
    pid = (await client.post("/api/projects", json={"title": "t", "topic": "산"})).json()["project"]["id"]
    assert (await client.post(f"/api/projects/{pid}/stages/script/run")).status_code == 202
    again = await client.post(f"/api/projects/{pid}/stages/script/run")
    assert again.status_code == 409


async def test_regenerate_returns_202_and_increments_attempt(client, db_session):
    from app.core.worker import StageWorker

    await _login(client, db_session, "c@example.com")
    pid = (await client.post("/api/projects", json={"title": "t", "topic": "커피"})).json()["project"]["id"]

    # 첫 실행을 워커로 완료시켜 NEEDS_REVIEW로 만든다.
    await client.post(f"/api/projects/{pid}/stages/script/run")
    stage_id = (await client.get(f"/api/projects/{pid}")).json()["stages"][0]["id"]
    await _drain(db_session, stage_id)

    regen = await client.post(f"/api/projects/{pid}/stages/script/regenerate")
    assert regen.status_code == 202
    body = regen.json()
    assert body["stages"][0]["attempt"] == 1
    assert body["stages"][0]["status"] == StageStatus.QUEUED


async def test_approve_still_returns_200(client, db_session):
    await _login(client, db_session, "approve@example.com")
    pid = (await client.post("/api/projects", json={"title": "t", "topic": "바다"})).json()["project"]["id"]
    await client.post(f"/api/projects/{pid}/stages/script/run")
    stage_id = (await client.get(f"/api/projects/{pid}")).json()["stages"][0]["id"]
    await _drain(db_session, stage_id)

    approved = await client.post(f"/api/projects/{pid}/stages/script/approve")
    assert approved.status_code == 200
    body = approved.json()
    assert body["stages"][0]["status"] == StageStatus.APPROVED
    assert body["project"]["current_stage"] == "voice"
    assert body["stages"][1]["status"] == StageStatus.PENDING


async def test_create_with_auto_run_queues_script(client, db_session):
    await _login(client, db_session, "autoapi@example.com")
    resp = await client.post(
        "/api/projects", json={"title": "t", "topic": "고래", "auto_run": True}
    )
    assert resp.status_code == 201
    assert resp.json()["stages"][0]["status"] == StageStatus.QUEUED
```

파일 상단 `_login` 아래에 헬퍼를 추가한다.

```python
async def _drain(db_session, stage_id: int):
    """API는 큐에 넣기만 한다. 테스트에서는 워커를 직접 한 번 돌려 완료시킨다."""
    from contextlib import asynccontextmanager

    from app.core.worker import StageWorker

    @asynccontextmanager
    async def _factory():
        yield db_session

    await StageWorker(session_factory=_factory).run_one(stage_id)
```

`tests/test_pipeline_run_stage.py`에서 `pipeline.run_stage`를 쓰는 테스트(`test_run_stage_success_sets_needs_review` · `test_run_stage_rejects_non_pending` · `test_approve_stage_registers_next_stage` · `test_regenerate_increments_attempt_and_reruns`)를 아래로 교체한다.

```python
async def _run_to_completion(session, project, stage, actor):
    """queue → claim → run 전체를 밟아 단계를 완료시킨다."""
    assert await pipeline.queue_stage(session, stage["id"], actor_id=actor)
    claimed = await pipeline.claim_stage(session, stage["id"], actor_id=actor)
    assert claimed is not None
    return await pipeline.run_claimed_stage(session, project, claimed, actor_id=actor)


@pytest.mark.asyncio
async def test_run_claimed_stage_success_sets_needs_review(db_session):
    actor, project, stage = await _seed_project_and_stage(db_session)
    updated = await _run_to_completion(db_session, project, stage, actor)
    assert updated["status"] == StageStatus.NEEDS_REVIEW
    assert updated["output"]["title"].startswith("바다 거북")
    assert updated["error"] is None


@pytest.mark.asyncio
async def test_queue_stage_rejects_approved(db_session):
    actor, project, stage = await _seed_project_and_stage(db_session, status=StageStatus.APPROVED)
    assert await pipeline.queue_stage(db_session, stage["id"], actor_id=actor) is False


@pytest.mark.asyncio
async def test_approve_stage_registers_next_stage(db_session):
    actor, project, stage = await _seed_project_and_stage(db_session)
    ran = await _run_to_completion(db_session, project, stage, actor)
    await pipeline.approve_stage(db_session, project, ran, actor_id=actor)
    conn = await raw_connection(db_session)
    proj = await queries.find_project_by_id(conn, id=project["id"])
    voice = await queries.find_stage(conn, project_id=project["id"], name=StageName.VOICE)
    assert proj["status"] == ProjectStatus.REVIEW
    assert proj["current_stage"] == StageName.VOICE
    assert voice["status"] == StageStatus.PENDING


@pytest.mark.asyncio
async def test_regenerate_increments_attempt_and_queues(db_session):
    actor, project, stage = await _seed_project_and_stage(db_session)
    ran = await _run_to_completion(db_session, project, stage, actor)
    await pipeline.regenerate_stage(db_session, project, ran, actor_id=actor)
    conn = await raw_connection(db_session)
    regen = pipeline.decode_stage(await queries.find_stage_by_id(conn, id=stage["id"]))
    assert regen["attempt"] == 1
    assert regen["status"] == StageStatus.QUEUED
```

- [ ] **Step 2: 테스트를 돌려 실패를 확인한다**

Run: `uv run pytest tests/test_api_projects.py tests/test_pipeline_run_stage.py -v`
Expected: FAIL — run이 200을 돌려주고 `NEEDS_REVIEW`가 나온다

- [ ] **Step 3: `regenerate_stage`가 실행 대신 큐에 넣게 한다**

`app/core/pipeline.py`에서 임시 `run_stage`를 **삭제**하고 `regenerate_stage`를 아래로 바꾼다.

```python
async def regenerate_stage(session, project: dict, stage: dict, actor_id: int) -> None:
    """검토 중인 단계를 되돌려 다시 큐에 태운다. NEEDS_REVIEW → PENDING → QUEUED."""
    if not can_transition(stage["status"], StageStatus.PENDING):
        raise AppError(409, "STAGE_CONFLICT", "재생성할 수 없는 상태입니다.")

    conn = await raw_connection(session)
    now = now_local()
    await queries.update_stage_run(
        conn, id=stage["id"], status=StageStatus.PENDING, output=json.dumps({}), error=None,
        attempt=stage["attempt"] + 1, started_at=None, finished_at=None,
        updated_at=now, updated_by=actor_id,
    )
    # 같은 트랜잭션에서 이어 큐로 올린다 — PENDING으로 멈춰 있는 순간이 밖에서 보이지 않는다.
    if not await queue_stage(session, stage["id"], actor_id):
        raise AppError(409, "STAGE_CONFLICT", "재생성할 수 없는 상태입니다.")
    await session.commit()
```

- [ ] **Step 4: API 엔드포인트를 고친다**

`app/api/projects.py`의 import에 추가한다.

```python
from app.core.worker import get_worker
```

`CreateProjectRequest`에 필드를 추가한다.

```python
class CreateProjectRequest(BaseModel):
    title: str
    topic: str
    auto_run: bool = False  # 켜면 검토 없이 4단계를 끝까지 진행한다
```

`create_project`의 `insert_project` 호출에서 `settings`를 바꾸고, 마지막에 자동 투입을 붙인다.

```python
        status=ProjectStatus.DRAFT, current_stage=StageName.SCRIPT,
        settings=json.dumps({"auto_run": body.auto_run}),
```

```python
    stage_id = await queries.insert_stage(...)   # 반환값을 받도록 바꾼다
    if body.auto_run:
        await pipeline.queue_stage(db, stage_id, actor_id=user["id"])
    await db.commit()
    if body.auto_run:
        get_worker().enqueue(stage_id)
    return await views.detail(conn, project_id)
```

`run_stage`·`regenerate_stage` 엔드포인트를 교체한다.

```python
@router.post("/{project_id}/stages/{name}/run", status_code=202)
async def run_stage(
    project_id: int, name: str, user: dict = Depends(current_user), db: AsyncSession = Depends(get_db)
):
    conn = await raw_connection(db)
    await _load_owned_project(conn, project_id, user["id"])
    stage = await _load_stage(conn, project_id, name)
    if not await pipeline.queue_stage(db, stage["id"], actor_id=user["id"]):
        # 코드는 기존과 같은 STAGE_CONFLICT를 유지한다(Errors.conflict는 CONFLICT라 다르다).
        raise AppError(409, "STAGE_CONFLICT", "이미 실행 중이거나 검토 단계입니다.")
    await db.commit()
    # 큐 투입은 커밋 이후 — 워커가 아직 안 보이는 행을 집으면 안 된다.
    get_worker().enqueue(stage["id"])
    return await views.detail(conn, project_id)


@router.post("/{project_id}/stages/{name}/regenerate", status_code=202)
async def regenerate_stage(
    project_id: int, name: str, user: dict = Depends(current_user), db: AsyncSession = Depends(get_db)
):
    conn = await raw_connection(db)
    project = await _load_owned_project(conn, project_id, user["id"])
    stage = await _load_stage(conn, project_id, name)
    await pipeline.regenerate_stage(db, project, stage, actor_id=user["id"])
    get_worker().enqueue(stage["id"])
    return await views.detail(conn, project_id)
```

`app/api/projects.py`의 import에 `AppError`를 더한다. `app/utils/errors.py`는 손대지 않는다 — `Errors.conflict`는 코드가 `CONFLICT`라 프론트가 보던 `STAGE_CONFLICT`와 다르다.

```python
from app.utils.errors import AppError, Errors
```

- [ ] **Step 5: lifespan으로 워커를 기동한다**

`app/main.py`를 고친다.

```python
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from app.api.health import router as health_router
from app.api.projects import router as projects_router
from app.auth.admin_router import router as admin_users_router
from app.auth.router import router as auth_router
from app.core.worker import get_worker
from app.utils.errors import DEFAULT_ERROR, AppError
from app.utils.logging import configure_logging

configure_logging()
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # 단계 실행은 요청이 아니라 이 워커가 맡는다. 기동 시 고아 상태도 여기서 정리된다.
    worker = get_worker()
    await worker.start()
    try:
        yield
    finally:
        await worker.stop()


app = FastAPI(title="Studio", lifespan=lifespan)
```

나머지(`include_router`, 예외 핸들러)는 그대로 둔다.

- [ ] **Step 6: 테스트를 돌려 통과를 확인한다**

Run: `uv run pytest -v`
Expected: PASS (전체). `ASGITransport`는 lifespan 이벤트를 보내지 않으므로 테스트에서 워커가 자동 기동하지 않는다 — 의도된 동작이다.

- [ ] **Step 7: 커밋**

```bash
git add app/api/projects.py app/main.py app/core/pipeline.py app/utils/errors.py tests/test_api_projects.py tests/test_pipeline_run_stage.py
git commit -m "기능: run/regenerate를 202 비동기로 전환하고 워커를 lifespan에 배선"
```

---

## Task 8: SSE 엔드포인트

**Files:**
- Modify: `app/api/projects.py`
- Test: `tests/test_api_events.py`

**Interfaces:**
- Consumes: `events.subscribe` · `events.get_progress` (Task 2), `views.detail` (Task 3)
- Produces: `GET /api/projects/{id}/events` — `text/event-stream`

- [ ] **Step 1: 실패하는 테스트를 쓴다**

`tests/test_api_events.py`를 만든다.

```python
import asyncio
import json

from app.auth.security import hash_password
from app.constants import UserRole, UserStatus
from app.core import events
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


def _parse(chunk: str) -> dict:
    assert chunk.startswith("data: ")
    return json.loads(chunk[len("data: "):])


async def test_events_requires_auth(client):
    async with client.stream("GET", "/api/projects/1/events") as resp:
        assert resp.status_code == 401


async def test_events_rejects_other_owner(client, db_session):
    await _login(client, db_session, "sse-owner@example.com")
    pid = (await client.post("/api/projects", json={"title": "t", "topic": "비밀"})).json()["project"]["id"]
    await _login(client, db_session, "sse-intruder@example.com")
    async with client.stream("GET", f"/api/projects/{pid}/events") as resp:
        assert resp.status_code == 404


async def test_events_sends_snapshot_then_published_event(client, db_session):
    await _login(client, db_session, "sse@example.com")
    pid = (await client.post("/api/projects", json={"title": "t", "topic": "달"})).json()["project"]["id"]

    async with client.stream("GET", f"/api/projects/{pid}/events") as resp:
        assert resp.status_code == 200
        assert resp.headers["content-type"].startswith("text/event-stream")
        lines = resp.aiter_lines()

        snapshot = _parse(await _next_data(lines))
        assert snapshot["type"] == "snapshot"
        assert snapshot["project"]["id"] == pid
        assert snapshot["stages"][0]["name"] == "script"
        assert snapshot["progress"] == {}

        # 구독이 붙은 뒤 발행한 이벤트가 그대로 흘러나와야 한다.
        events.publish(pid, {"type": "progress", "stage": "script",
                             "percent": None, "message": "대본을 생성하는 중…"})
        pushed = _parse(await _next_data(lines))
        assert pushed["message"] == "대본을 생성하는 중…"


async def _next_data(lines) -> str:
    """빈 줄과 keep-alive 코멘트를 건너뛰고 다음 data: 줄을 돌려준다."""
    async for line in lines:
        if line.startswith("data: "):
            return line
    raise AssertionError("data 줄이 오지 않았다")
```

> `events.publish`는 서버와 같은 이벤트 루프에서 불려야 한다. `ASGITransport`는 인-프로세스라 그대로 동작한다.

- [ ] **Step 2: 테스트를 돌려 실패를 확인한다**

Run: `uv run pytest tests/test_api_events.py -v`
Expected: FAIL — 404 (라우트 없음)

- [ ] **Step 3: 엔드포인트를 만든다**

`app/api/projects.py` 상단에 추가한다.

```python
import asyncio

from fastapi.responses import FileResponse, StreamingResponse

from app.core import events
```

`get_stage_asset` 앞에 아래를 추가한다.

```python
# 프록시 유휴 타임아웃을 막고 끊긴 클라이언트를 감지하는 간격.
_PING_INTERVAL_SEC = 15.0


def _sse(event: dict) -> str:
    return f"data: {json.dumps(event, ensure_ascii=False)}\n\n"


@router.get("/{project_id}/events")
async def project_events(
    project_id: int, user: dict = Depends(current_user), db: AsyncSession = Depends(get_db)
):
    conn = await raw_connection(db)
    await _load_owned_project(conn, project_id, user["id"])  # 남의 프로젝트면 404
    snapshot = await views.detail(conn, project_id)
    # 접속 직후 현재 상태를 통째로 한 번 보낸다 → 프론트는 GET detail과 SSE의
    # 도착 순서를 신경 쓸 필요가 없다. 진행 중인 단계의 마지막 진행률도 함께 싣는다.
    snapshot["type"] = "snapshot"
    snapshot["progress"] = {
        stage["name"]: progress
        for stage in snapshot["stages"]
        if (progress := events.get_progress(stage["id"])) is not None
    }

    # SSE는 몇 시간씩 열려 있다. DB 작업은 여기서 끝났으므로 커넥션을 풀에 돌려준다
    # (안 그러면 접속자 수만큼 풀이 잠긴다). get_db의 정리는 중복 close라 무해하다.
    await db.close()

    async def stream():
        # 스냅샷을 읽기 전에 먼저 구독한다. 반대 순서면 그 사이의 suspension point에서
        # 워커가 발행한 이벤트가 빈 구독자 집합으로 가 영영 유실된다(재생이 없으므로
        # 터미널 이벤트를 놓치면 화면이 RUNNING에 멈춘다). 전송 순서는 그대로
        # "스냅샷 먼저" — 등록 순서만 앞당긴다.
        async with events.subscribe(project_id) as queue:
            snapshot = await _build_snapshot(conn, project_id)  # 구독 이후에 읽는다
            await db.close()
            yield _sse(snapshot)
            while True:
                try:
                    event = await asyncio.wait_for(queue.get(), timeout=_PING_INTERVAL_SEC)
                except TimeoutError:
                    yield ": ping\n\n"
                    continue
                yield _sse(event)

    return StreamingResponse(
        stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
```

- [ ] **Step 4: 테스트를 돌려 통과를 확인한다**

Run: `uv run pytest tests/test_api_events.py -v`
Expected: PASS (3 passed)

- [ ] **Step 5: 전체 테스트를 돌린다**

Run: `uv run pytest -v`
Expected: PASS

- [ ] **Step 6: 커밋**

```bash
git add app/api/projects.py tests/test_api_events.py
git commit -m "기능: 프로젝트 SSE 엔드포인트(스냅샷 + 실시간 이벤트) 추가"
```

---

## Task 9: provider 진행률 — script · voice · captions

**Files:**
- Modify: `app/providers/script/openai.py`, `app/providers/script/claude.py`, `app/providers/script/fake.py`
- Modify: `app/providers/voice/edge_tts.py`
- Modify: `app/providers/captions/whisper.py`
- Test: `tests/test_provider_captions_whisper.py`, `tests/test_provider_voice_edge_tts.py`

**Interfaces:**
- Consumes: `StageContext.on_progress` (Task 4)
- Produces: 없음 (기존 provider의 동작 보강)

- [ ] **Step 1: 실패하는 테스트를 쓴다**

`tests/test_provider_captions_whisper.py`의 `_fake_transcribe`와 `_ctx`를 아래로 바꾸고(진짜 `_transcribe`가 콜백을 받게 되므로 가짜도 시그니처를 맞춰야 한다), 테스트를 하나 추가한다.

```python
def _fake_transcribe(audio_path: str, model_size: str, on_progress):
    _calls.append({"audio_path": audio_path, "model_size": model_size})
    on_progress(50.0, "받아쓰는 중…")
    words = [{"w": "안녕", "s": 0.0, "e": 0.5}, {"w": "하세요", "s": 0.5, "e": 1.1}]
    on_progress(100.0, "받아쓰는 중…")
    return words, "ko", 1.2


def _ctx(on_progress=None) -> StageContext:
    kwargs = {"on_progress": on_progress} if on_progress else {}
    return StageContext(
        topic="t", input_assets=_ASSETS, workdir="projects/9/captions", **kwargs
    )
```

```python
@pytest.mark.asyncio
async def test_run_forwards_progress_callback(monkeypatch, tmp_path):
    # 세그먼트를 소비할 때마다 "여기까지 왔다"가 밖으로 나가야 한다.
    monkeypatch.setattr(storage, "_root", lambda: tmp_path)
    seen: list[tuple[float | None, str]] = []
    await WhisperCaptions(transcribe=_fake_transcribe).run(
        _ctx(on_progress=lambda p, m: seen.append((p, m)))
    )
    assert seen == [(50.0, "받아쓰는 중…"), (100.0, "받아쓰는 중…")]
```

`tests/test_provider_voice_edge_tts.py`에 추가한다.

```python
@pytest.mark.asyncio
async def test_run_reports_message_without_percent(monkeypatch, tmp_path):
    # edge-tts는 전체 길이를 알려주지 않는다 — 진짜 %가 없으므로 None을 보낸다.
    monkeypatch.setattr(storage, "_root", lambda: tmp_path)
    seen: list[tuple[float | None, str]] = []
    ctx = StageContext(
        topic="t", inputs={"script": _SCRIPT}, workdir="projects/5/voice",
        on_progress=lambda p, m: seen.append((p, m)),
    )
    await EdgeTTS(communicate_factory=_FakeCommunicate).run(ctx)
    assert seen == [(None, "음성 합성 중…")]
```

- [ ] **Step 2: 테스트를 돌려 실패를 확인한다**

Run: `uv run pytest tests/test_provider_captions_whisper.py tests/test_provider_voice_edge_tts.py -v`
Expected: FAIL — `seen`이 비어 있다 (`assert []`)

- [ ] **Step 3: whisper에 세그먼트 진행률을 붙인다**

`app/providers/captions/whisper.py`의 `_transcribe`와 `run`을 바꾼다.

```python
def _transcribe(audio_path: str, model_size: str, on_progress) -> tuple[list[dict], str, float]:
    """오디오를 받아써 (단어들, 언어, 길이)를 돌려준다. CPU 블로킹 호출."""
    segments, info = _load_model(model_size).transcribe(
        audio_path, language=_LANGUAGE, word_timestamps=True
    )
    # segments는 지연 제너레이터다 — 이 스레드 안에서 끝까지 소비해야 한다.
    # 소비하면서 세그먼트 끝시각/전체 길이로 진행률을 보고한다.
    words: list[dict] = []
    for segment in segments:
        words.extend(
            {"w": word.word.strip(), "s": round(word.start, 3), "e": round(word.end, 3)}
            for word in (segment.words or [])
            if word.word.strip()
        )
        if info.duration:
            on_progress(min(100.0, segment.end / info.duration * 100), _PROGRESS_MESSAGE)
    return words, info.language, round(info.duration, 3)
```

파일 상단 상수 옆에 추가한다.

```python
_PROGRESS_MESSAGE = "받아쓰는 중…"
```

`run`의 `asyncio.to_thread` 호출에 콜백을 넘긴다.

```python
        words, language, duration = await asyncio.to_thread(
            self._transcribe, str(audio), model_size, ctx.on_progress
        )
```

- [ ] **Step 4: voice·script에 메시지를 붙인다**

`app/providers/voice/edge_tts.py`의 `run` 첫 줄에 추가한다.

```python
    async def run(self, ctx: StageContext) -> StageResult:
        # edge-tts는 전체 길이를 알려주지 않는다 — 진짜 %가 없으므로 메시지만 보낸다.
        ctx.on_progress(None, "음성 합성 중…")
        text = narration_text(ctx.inputs)
```

`app/providers/script/openai.py` · `claude.py` · `fake.py`의 `run` 첫 줄에 각각 추가한다.

```python
        ctx.on_progress(None, "대본을 생성하는 중…")  # LLM 단일 호출이라 진짜 %가 없다
```

- [ ] **Step 5: 테스트를 돌려 통과를 확인한다**

Run: `uv run pytest tests/test_provider_captions_whisper.py tests/test_provider_voice_edge_tts.py tests/test_provider_script_fake.py tests/test_provider_script_openai.py tests/test_provider_script_claude.py -v`
Expected: PASS

- [ ] **Step 6: 커밋**

```bash
git add app/providers tests/test_provider_captions_whisper.py tests/test_provider_voice_edge_tts.py
git commit -m "기능: script·voice·captions provider가 진행 상황을 보고"
```

---

## Task 10: ffmpeg 진행률 — `-progress pipe:1`

**Files:**
- Modify: `app/utils/ffmpeg.py`
- Modify: `app/providers/render/slideshow.py`
- Test: `tests/test_ffmpeg.py`

**Interfaces:**
- Consumes: `StageContext.on_progress` (Task 4)
- Produces:
  - `ffmpeg.parse_progress_percent(line: str, total_sec: float | None) -> float | None`
  - `ffmpeg.run(cmd, cwd, on_progress=None, total_sec=None) -> None`

- [ ] **Step 1: 실패하는 테스트를 쓴다**

`tests/test_ffmpeg.py`에 추가한다.

이 파일에는 이미 `_cmd()` 헬퍼가 있다. 그것을 그대로 쓴다. import 한 줄을 더한다.

```python
from app.utils.ffmpeg import build_slideshow_cmd, parse_progress_percent
```

```python
def test_cmd_asks_ffmpeg_for_progress():
    # 진행률을 stdout으로 받아야 파싱할 수 있다.
    cmd = _cmd()
    assert cmd[cmd.index("-progress") + 1] == "pipe:1"


def test_parse_progress_percent_reads_out_time_us():
    assert parse_progress_percent("out_time_us=5000000\n", 10.0) == 50.0


def test_parse_progress_percent_clamps_to_100():
    # -shortest로 끝나는 순간 out_time이 총 길이를 살짝 넘을 수 있다.
    assert parse_progress_percent("out_time_us=11000000\n", 10.0) == 100.0


def test_parse_progress_percent_ignores_other_lines():
    assert parse_progress_percent("frame=120\n", 10.0) is None
    assert parse_progress_percent("out_time_us=N/A\n", 10.0) is None  # 시작 직후엔 N/A가 온다
    # 총 길이를 모르면 %를 낼 수 없다.
    assert parse_progress_percent("out_time_us=5000000\n", None) is None
```

- [ ] **Step 2: 테스트를 돌려 실패를 확인한다**

Run: `uv run pytest tests/test_ffmpeg.py -v`
Expected: FAIL — `-progress` 미포함, `parse_progress_percent` 없음

- [ ] **Step 3: `app/utils/ffmpeg.py`를 고친다**

`build_slideshow_cmd`의 반환 리스트 앞부분에 두 인자를 넣는다.

```python
    return [
        exe, "-y",
        "-progress", "pipe:1",   # 진행 상황을 stdout으로 — 아래 run()이 파싱한다
        "-f", "lavfi", "-i", f"color=c={bg_color}:s={width}x{height}",
        ...
    ]
```

`run`을 아래로 교체한다.

```python
def parse_progress_percent(line: str, total_sec: float | None) -> float | None:
    """ffmpeg -progress 한 줄에서 진행률(0~100)을 뽑는다. 진행 정보가 아니면 None."""
    key, _, value = line.partition("=")
    if key.strip() != "out_time_us" or not total_sec:
        return None
    try:
        elapsed_sec = int(value.strip()) / 1_000_000
    except ValueError:
        return None  # 시작 직후엔 N/A가 온다
    return max(0.0, min(100.0, elapsed_sec / total_sec * 100))


async def run(cmd: list[str], cwd: str, on_progress=None, total_sec: float | None = None) -> None:
    """ffmpeg를 실행한다. 0이 아닌 종료코드면 RuntimeError. 블로킹이라 스레드로 비켜준다."""

    def _run() -> tuple[int, str]:
        import subprocess
        from collections import deque

        try:
            proc = subprocess.Popen(
                cmd, cwd=cwd,
                stdout=subprocess.PIPE,
                # stderr를 따로 파이프로 받으면, stdout을 다 읽는 동안 ffmpeg의 방대한
                # 로그가 stderr 버퍼를 채워 서로 막힌다(교착). 한 스트림으로 합쳐 읽는다.
                stderr=subprocess.STDOUT,
                text=True, encoding="utf-8", errors="replace",
            )
        except OSError as exc:
            raise RuntimeError(f"ffmpeg 실행 불가: {exc}") from exc

        tail: deque[str] = deque(maxlen=40)  # 실패 메시지로 쓸 마지막 로그
        for line in proc.stdout:
            tail.append(line.rstrip())
            percent = parse_progress_percent(line, total_sec)
            if percent is not None and on_progress is not None:
                on_progress(percent, "영상 합성 중…")
        proc.stdout.close()
        return proc.wait(), "\n".join(tail)

    code, log = await asyncio.to_thread(_run)
    if code != 0:
        raise RuntimeError(f"ffmpeg 실패(code={code}): {log}")
```

- [ ] **Step 4: `SlideshowRender`가 콜백과 길이를 넘기게 한다**

`app/providers/render/slideshow.py:48`의 러너 호출 한 줄을 아래로 바꾼다. 아래에 이미 있는 `duration` 계산을 위로 끌어올려 진행률 분모로 재사용한다.

```python
        # captions가 잰 길이를 진행률 분모로 쓴다. 없으면 %는 못 내고 메시지만 나간다.
        duration = ctx.inputs.get("captions", {}).get("duration_sec")
        ctx.on_progress(None, "영상 합성 중…")
        # cwd를 저장소 루트로 둬야 상대경로 자막 필터가 동작한다(Windows ':' 회피).
        await self._runner(
            cmd, str(storage.resolve(".")), on_progress=ctx.on_progress, total_sec=duration
        )

        size = out_abs.stat().st_size
```

그 아래에 남아 있는 `duration = ctx.inputs.get(...)` 한 줄은 지운다 (위로 올렸다).

> `tests/test_provider_render_slideshow.py`가 주입하는 가짜 러너의 시그니처도 맞춰야 한다. 기존 `async def _fake(cmd, cwd)` 형태를 `async def _fake(cmd, cwd, on_progress=None, total_sec=None)`으로 넓힌다.

- [ ] **Step 5: 테스트를 돌려 통과를 확인한다**

Run: `uv run pytest tests/test_ffmpeg.py tests/test_provider_render_slideshow.py tests/test_render_smoke.py -v`
Expected: PASS. 스모크(`-m slow`)까지 통과해야 실제 ffmpeg가 `-progress`를 받아들이는 것이 확인된다.

- [ ] **Step 6: 커밋**

```bash
git add app/utils/ffmpeg.py app/providers/render/slideshow.py tests/test_ffmpeg.py tests/test_provider_render_slideshow.py
git commit -m "기능: ffmpeg -progress 파싱으로 render 단계 진행률 보고"
```

---

## Task 11: 프론트 `lib/events.ts` + 타입

**Files:**
- Create: `web/src/lib/events.ts`
- Modify: `web/src/lib/projects.ts`

**Interfaces:**
- Consumes: `GET /api/projects/{id}/events` (Task 8), `projects.detail` (기존)
- Produces:
  - `subscribeProject(id: number, onEvent: (e: ProjectEvent) => void): () => void`
  - `type StageProgress = { percent: number | null; message: string }`
  - `type ProjectEvent` (snapshot | stage | progress)
  - `projects.create(body: { title, topic, auto_run })`
  - `STAGE_BADGE.QUEUED`

- [ ] **Step 1: 타입과 배지를 넓힌다**

`web/src/lib/projects.ts`를 고친다.

```ts
export type StageStatus = 'PENDING' | 'QUEUED' | 'RUNNING' | 'NEEDS_REVIEW' | 'APPROVED' | 'FAILED'
```

```ts
  create: (body: { title: string; topic: string; auto_run: boolean }) =>
    api.post<ProjectDetail>('/projects', body),
```

```ts
export const STAGE_BADGE: Record<StageStatus, { label: string; className: string }> = {
  PENDING: { label: '대기', className: 'bg-slate-100 text-slate-600' },
  QUEUED: { label: '대기열', className: 'bg-indigo-100 text-indigo-800' },
  RUNNING: { label: '실행 중', className: 'bg-blue-100 text-blue-800' },
  NEEDS_REVIEW: { label: '검토 필요', className: 'bg-yellow-100 text-yellow-800' },
  APPROVED: { label: '승인됨', className: 'bg-green-100 text-green-800' },
  FAILED: { label: '실패', className: 'bg-red-100 text-red-800' },
}
```

- [ ] **Step 2: `web/src/lib/events.ts`를 만든다**

```ts
import { projects, type ProjectDetail, type Stage } from './projects'

export type StageProgress = { percent: number | null; message: string }

export type ProjectEvent =
  | ({ type: 'snapshot'; progress: Record<string, StageProgress> } & ProjectDetail)
  | { type: 'stage'; project: ProjectDetail['project']; stage: Stage }
  | ({ type: 'progress'; stage: string } & StageProgress)

const FIRST_BACKOFF_MS = 1000
const MAX_BACKOFF_MS = 30_000

// 프로젝트 상세 화면의 실시간 구독. 정리 함수를 돌려준다.
//
// EventSource는 401을 받아도 스스로 무한히 재접속한다. 그래서 오류가 나면 직접 닫고,
// 다시 붙기 전에 평범한 API를 한 번 태운다 — api.ts의 401→refresh→재시도가 거기서
// 쿠키를 갱신해 준다. 그마저 실패하면(로그아웃 등) 백오프를 늘리며 물러선다.
export function subscribeProject(id: number, onEvent: (e: ProjectEvent) => void): () => void {
  let source: EventSource | null = null
  let timer: ReturnType<typeof setTimeout> | null = null
  let backoff = FIRST_BACKOFF_MS
  let closed = false

  const retryLater = () => {
    if (closed) return
    timer = setTimeout(reconnect, backoff)
    backoff = Math.min(backoff * 2, MAX_BACKOFF_MS)
  }

  const connect = () => {
    if (closed) return
    source = new EventSource(`/api/projects/${id}/events`)
    source.onopen = () => {
      backoff = FIRST_BACKOFF_MS
    }
    source.onmessage = (e) => onEvent(JSON.parse(e.data) as ProjectEvent)
    source.onerror = () => {
      source?.close()
      source = null
      retryLater()
    }
  }

  const reconnect = async () => {
    if (closed) return
    try {
      await projects.detail(id)
    } catch {
      retryLater()
      return
    }
    connect()
  }

  connect()

  return () => {
    closed = true
    if (timer) clearTimeout(timer)
    source?.close()
  }
}
```

- [ ] **Step 3: 타입 검사와 빌드를 돌린다**

Run: `npm run lint && npm run build`
Expected: 오류 없음. `projects.create` 호출부(`NewProjectModal.tsx`)가 `auto_run` 누락으로 타입 오류를 낼 텐데, Task 13에서 고친다 — 지금은 임시로 `auto_run: false`를 넘겨 빌드를 통과시킨다.

```ts
      await projects.create({ title: title.trim(), topic: topic.trim(), auto_run: false })
```

- [ ] **Step 4: 커밋**

```bash
git add web/src/lib/events.ts web/src/lib/projects.ts web/src/pages/projects/NewProjectModal.tsx
git commit -m "기능: 프론트 SSE 구독 래퍼와 QUEUED 상태 타입 추가"
```

---

## Task 12: 프론트 진행률 UI

**Files:**
- Modify: `web/src/pages/projects/ProjectDetail.tsx`

**Interfaces:**
- Consumes: `subscribeProject` · `StageProgress` (Task 11)
- Produces: 없음

- [ ] **Step 1: 진행률 바 컴포넌트를 추가한다**

`ProjectDetail.tsx`의 `StageBadge` 아래에 넣는다.

```tsx
function ProgressBar({ progress }: { progress: StageProgress }) {
  const { percent, message } = progress
  return (
    <div className="mt-3 space-y-1">
      <div className="h-1.5 w-full overflow-hidden rounded-full bg-slate-100">
        {percent === null ? (
          // 진짜 진행률이 없는 단계(대본·음성) — 가짜 숫자 대신 움직이는 띠를 보여준다.
          <div className="h-full w-1/3 animate-pulse rounded-full bg-blue-400" />
        ) : (
          <div
            className="h-full rounded-full bg-blue-500 transition-[width] duration-300"
            style={{ width: `${percent}%` }}
          />
        )}
      </div>
      <div className="text-xs text-slate-500">
        {message}
        {percent !== null && ` ${Math.round(percent)}%`}
      </div>
    </div>
  )
}
```

- [ ] **Step 2: `StageCard`가 진행률을 받게 한다**

props에 `progress`를 더하고, 실행 중일 때 바를 그린다.

```tsx
function StageCard({
  projectId,
  stage,
  voiceAttempt,
  progress,
  acting,
  act,
}: {
  projectId: number
  stage: Stage
  voiceAttempt: number | null
  progress: StageProgress | undefined
  acting: boolean
  act: (fn: () => Promise<Detail>) => Promise<void>
}) {
```

`FAILED` 오류 표시 바로 위에 넣는다.

```tsx
      {(stage.status === 'QUEUED' || stage.status === 'RUNNING') && (
        <ProgressBar progress={progress ?? { percent: null, message: '대기 중…' }} />
      )}
```

- [ ] **Step 3: 구독을 붙이고 `acting`을 축소한다**

`ProjectDetail` 본문을 아래로 바꾼다 (`load`/`act`/렌더).

```tsx
export function ProjectDetail() {
  const { id } = useParams<{ id: string }>()
  const projectId = Number(id)
  const [detail, setDetail] = useState<Detail | null>(null)
  const [progress, setProgress] = useState<Record<string, StageProgress>>({})
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [acting, setActing] = useState(false)

  useEffect(() => {
    setLoading(true)
    setError(null)
    // 첫 화면은 SSE의 snapshot이 채운다. 실패는 구독 래퍼가 재시도로 흡수한다.
    const unsubscribe = subscribeProject(projectId, (event) => {
      setLoading(false)
      if (event.type === 'snapshot') {
        setDetail({ project: event.project, stages: event.stages })
        setProgress(event.progress)
        return
      }
      if (event.type === 'stage') {
        setDetail((prev) =>
          prev === null
            ? prev
            : {
                project: event.project,
                stages: prev.stages.some((s) => s.id === event.stage.id)
                  ? prev.stages.map((s) => (s.id === event.stage.id ? event.stage : s))
                  : [...prev.stages, event.stage],
              },
        )
        // 단계가 끝났으면 진행률을 지운다 — 다음 실행의 잔상이 남지 않게.
        if (event.stage.status !== 'QUEUED' && event.stage.status !== 'RUNNING') {
          setProgress((prev) => {
            const { [event.stage.name]: _done, ...rest } = prev
            return rest
          })
        }
        return
      }
      setProgress((prev) => ({
        ...prev,
        [event.stage]: { percent: event.percent, message: event.message },
      }))
    })
    return unsubscribe
  }, [projectId])

  // 요청을 보내는 동안만 잠근다. 실행 완료를 기다리지 않는다 — 결과는 SSE로 온다.
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
```

`StageCard` 호출에 `progress`를 넘긴다.

```tsx
          <StageCard
            key={s.id}
            projectId={projectId}
            stage={s}
            voiceAttempt={voiceAttempt}
            progress={progress[s.name]}
            acting={acting}
            act={act}
          />
```

`[실행]` 버튼의 라벨에서 대기 문구를 뺀다 (더 이상 기다리지 않는다).

```tsx
              {acting ? '요청 중…' : '실행'}
```

import를 더한다.

```tsx
import { subscribeProject, type StageProgress } from '../../lib/events'
```

`useCallback`·`projects.detail` import가 더 이상 안 쓰이면 지운다.

- [ ] **Step 4: 타입 검사와 빌드를 돌린다**

Run: `npm run lint && npm run build`
Expected: 오류 없음

- [ ] **Step 5: 실제 앱으로 확인한다**

```
docker compose up -d db
npm run migrate
npm run dev
```

브라우저에서 프로젝트를 하나 만들고 [실행]을 누른다. 확인할 것:
1. 버튼이 즉시 풀리고 배지가 **대기열 → 실행 중 → 검토 필요**로 스스로 바뀐다.
2. `captions` 단계에서 진행률 바가 실제로 차오른다 (`.env`의 `CAPTIONS_PROVIDER=whisper`일 때).
3. 실행 도중 **페이지를 새로고침**해도 진행 중 상태와 진행률이 그대로 보인다.
4. 개발자도구 Network에서 `events` 요청이 열린 채 유지되고 15초마다 ping이 들어온다.

- [ ] **Step 6: 커밋**

```bash
git add web/src/pages/projects/ProjectDetail.tsx
git commit -m "기능: 프로젝트 상세가 SSE로 상태·진행률을 실시간 반영"
```

---

## Task 13: 자동 진행 체크박스 + 문서

**Files:**
- Modify: `web/src/pages/projects/NewProjectModal.tsx`
- Modify: `README.md`

**Interfaces:**
- Consumes: `projects.create({ title, topic, auto_run })` (Task 11), `POST /api/projects`의 `auto_run` (Task 7)
- Produces: 없음

- [ ] **Step 1: 체크박스를 붙인다**

`NewProjectModal.tsx`를 고친다.

```tsx
  const [autoRun, setAutoRun] = useState(false)
```

```tsx
      await projects.create({ title: title.trim(), topic: topic.trim(), auto_run: autoRun })
```

`topic` 필드 아래, `{error && ...}` 위에 넣는다.

```tsx
        <label className="flex items-start gap-2 text-sm text-slate-700">
          <input
            type="checkbox"
            checked={autoRun}
            onChange={(e) => setAutoRun(e.target.checked)}
            className="mt-0.5"
          />
          <span>
            자동으로 끝까지 진행
            <span className="block text-xs text-slate-400">
              대본·음성·자막·영상을 검토 없이 이어서 만듭니다. 중간에 실패하면 멈춥니다.
            </span>
          </span>
        </label>
```

- [ ] **Step 2: 타입 검사와 빌드를 돌린다**

Run: `npm run lint && npm run build`
Expected: 오류 없음

- [ ] **Step 3: README를 갱신한다**

"인프라" 절의 procrastinate 언급을 현재 구조로 바꾼다.

```markdown
- **PostgreSQL 하나로 통일** — 데이터 저장과 작업 큐(`stages` 테이블)를 모두 담당해 Redis가 필요 없다. 로컬은 `docker compose`로 기동.
- **단계 실행은 앱 내 백그라운드 워커**가 맡는다(`app/core/worker.py`). 별도 프로세스 없이 FastAPI `lifespan`에서 함께 뜨고, 상태·진행률은 SSE(`GET /api/projects/{id}/events`)로 UI에 푸시된다. 동시 실행 수는 `.env`의 `WORKER_CONCURRENCY`(기본 1)로 조절한다.
```

"개발 실행" 절 끝에 한 줄 덧붙인다.

```markdown
> 앱이 뜰 때 이전 실행에서 `RUNNING`으로 남은 단계는 자동으로 실패 처리된다(중간 산출물 상태를 알 수 없기 때문). 상세 화면에서 다시 실행하면 된다.
```

- [ ] **Step 4: 자동 진행을 실제로 확인한다**

`npm run dev` 상태에서 새 프로젝트를 "자동으로 끝까지 진행"을 켜고 만든다. 확인할 것:
1. 만들자마자 `script`가 **대기열**로 시작한다 ([실행]을 안 눌러도).
2. 4단계가 스스로 이어지고 각 단계가 승인됨으로 바뀐다.
3. 마지막에 프로젝트가 완료(`DONE`)가 되고 mp4를 내려받을 수 있다.

- [ ] **Step 5: 전체 테스트를 돌린다**

Run: `uv run pytest -v`
Expected: PASS (전체)

- [ ] **Step 6: 커밋**

```bash
git add web/src/pages/projects/NewProjectModal.tsx README.md
git commit -m "기능: 프로젝트 생성 시 자동 진행 옵션 + 워커·SSE 문서 반영"
```

---

## 남은 리스크 (구현 중 확인)

1. **Vite 개발 프록시의 SSE 버퍼링** — Task 12 Step 5에서 이벤트가 뭉쳐 도착하면 `web/vite.config.ts`의 프록시를 객체 형태로 바꿔 확인한다. 운영에서는 리버스 프록시의 버퍼링 설정(`X-Accel-Buffering: no`는 이미 보내고 있다)을 함께 본다.
2. **워커 종료 시 ffmpeg 좀비** — `stop()`이 5초 뒤 태스크를 취소하면 `asyncio.to_thread` 안의 `subprocess`는 즉시 죽지 않는다. Task 13 확인 중 Ctrl+C로 앱을 내려 보고 남은 ffmpeg 프로세스가 있는지 확인한다. 남으면 `Popen`을 붙잡아 `terminate()`하는 처리를 추가한다.
3. **DB 커넥션 풀과 SSE** — Task 8에서 `await db.close()`로 즉시 반납하지만, 여러 탭에서 오래 열어 두고 풀 고갈이 없는지 실측한다.
