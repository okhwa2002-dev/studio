import json
from contextlib import asynccontextmanager

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
    _, _, stage_id = await _seed(db_session, "w1@example.com")
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
    _, _, stage_id = await _seed(db_session, "w3@example.com")
    worker = StageWorker(session_factory=_factory(db_session))
    await worker.run_one(stage_id)  # PENDING이므로 claim 실패 — 조용히 버려진다

    conn = await raw_connection(db_session)
    assert dict(await queries.find_stage_by_id(conn, id=stage_id))["status"] == StageStatus.PENDING

    # 큐에 같은 id가 두 번 들어가는 경우: 정상적으로 한 번 실행해 NEEDS_REVIEW까지
    # 보낸 뒤, 같은 id로 run_one을 다시 불러도(중복 enqueue) claim_stage가 None을
    # 돌려주므로 두 번째 실행은 조용히 버려지고 상태가 바뀌지 않는다.
    await pipeline.queue_stage(db_session, stage_id, actor_id=None)
    await db_session.commit()
    await worker.run_one(stage_id)
    assert dict(await queries.find_stage_by_id(conn, id=stage_id))["status"] == StageStatus.NEEDS_REVIEW

    await worker.run_one(stage_id)
    assert dict(await queries.find_stage_by_id(conn, id=stage_id))["status"] == StageStatus.NEEDS_REVIEW


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


async def test_worker_start_enqueue_stop_drains_queue(db_session):
    # enqueue → _loop → stop()의 유예를 실제 루프로 한 번에 확인한다.
    _, _, stage_id = await _seed(db_session, "w7@example.com")
    worker = StageWorker(session_factory=_factory(db_session), concurrency=1)

    # 이 시점엔 QUEUED가 없으므로 start()의 _recover()는 아무것도 다시 넣지 않는다.
    await worker.start()
    await pipeline.queue_stage(db_session, stage_id, actor_id=None)
    await db_session.commit()
    worker.enqueue(stage_id)

    await worker.stop()

    conn = await raw_connection(db_session)
    stage = dict(await queries.find_stage_by_id(conn, id=stage_id))
    assert stage["status"] == StageStatus.NEEDS_REVIEW


async def test_worker_loop_survives_run_one_exception(db_session, monkeypatch):
    # 한 단계의 run_one 실패가 뒤에 이어지는 단계 처리를 막지 않아야 한다.
    _, _, stage_id = await _seed(db_session, "w8@example.com")
    await pipeline.queue_stage(db_session, stage_id, actor_id=None)
    await db_session.commit()

    worker = StageWorker(session_factory=_factory(db_session), concurrency=1)
    real_run_one = worker.run_one

    async def _flaky(id_):
        if id_ == -1:
            raise RuntimeError("의도적 실패 — 존재하지 않는 stage id")
        return await real_run_one(id_)

    monkeypatch.setattr(worker, "run_one", _flaky)

    await worker.start()
    worker.enqueue(-1)
    worker.enqueue(stage_id)
    await worker.stop()

    conn = await raw_connection(db_session)
    stage = dict(await queries.find_stage_by_id(conn, id=stage_id))
    assert stage["status"] == StageStatus.NEEDS_REVIEW


async def test_auto_run_approves_and_queues_next_stage(db_session):
    _, project_id, stage_id = await _seed(
        db_session, "auto1@example.com", settings={"auto_run": True}
    )
    await pipeline.queue_stage(db_session, stage_id, actor_id=None)
    await db_session.commit()

    worker = StageWorker(session_factory=_factory(db_session))
    async with events.subscribe(project_id) as queue:
        await worker.run_one(stage_id)
        received = []
        while not queue.empty():
            received.append(queue.get_nowait())

    conn = await raw_connection(db_session)
    script = dict(await queries.find_stage_by_id(conn, id=stage_id))
    voice = dict(await queries.find_stage(conn, project_id=project_id, name=StageName.VOICE))
    assert script["status"] == StageStatus.APPROVED
    assert voice["status"] == StageStatus.QUEUED
    # 재귀가 아니라 큐를 경유해야 한다 — 스택이 쌓이면 안 된다.
    assert worker._queue.get_nowait() == voice["id"]

    # "상태 변화를 브라우저로 민다"가 이 브랜치의 헤드라인이다 — 자동 승인 연쇄가
    # DB만 바꾸고 이벤트 발행을 빼먹으면 화면이 갱신되지 않는다. 두 이벤트 모두 고정한다.
    stage_events = [(e["stage"]["name"], e["stage"]["status"]) for e in received if e["type"] == "stage"]
    assert (StageName.SCRIPT, StageStatus.APPROVED) in stage_events
    assert (StageName.VOICE, StageStatus.QUEUED) in stage_events


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


async def test_auto_run_last_stage_marks_project_done_without_enqueue(db_session, monkeypatch):
    # 브리프의 세 테스트가 다루지 않는 분기: 마지막(render) 단계를 자동 승인하면
    # _chain_if_auto의 next_stage가 None이라 큐에 아무것도 넣지 않아야 하고,
    # 프로젝트는 approve_stage 경로를 통해 DONE이 되어야 한다.
    from app.providers.base import StageResult
    from app.providers.render.fake import FakeRender

    async def _fake_run(self, ctx):
        # 실제 오디오/자막 산출물 없이도 성공 경로만 확인하면 되므로 입력 검증을 건너뛴다.
        return StageResult(output={"provider": "fake"}, assets=[])

    monkeypatch.setattr(FakeRender, "run", _fake_run)

    conn = await raw_connection(db_session)
    now = now_local()
    user = User(email="auto3@example.com", password_hash=hash_password("pw12345"),
                role=UserRole.MEMBER, status=UserStatus.ACTIVE)
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)

    project_id = await queries.insert_project(
        conn, owner_id=user.id, title="t", topic="바다 거북",
        status=ProjectStatus.REVIEW, current_stage=StageName.RENDER,
        settings=json.dumps({"auto_run": True}),
        created_at=now, updated_at=now, created_by=user.id, updated_by=user.id,
    )
    stage_id = await queries.insert_stage(
        conn, project_id=project_id, name=StageName.RENDER, provider="fake",
        status=StageStatus.PENDING, output=json.dumps({}), error=None, attempt=0,
        started_at=None, finished_at=None,
        created_at=now, updated_at=now, created_by=user.id, updated_by=user.id,
    )
    await db_session.commit()

    await pipeline.queue_stage(db_session, stage_id, actor_id=None)
    await db_session.commit()

    worker = StageWorker(session_factory=_factory(db_session))
    await worker.run_one(stage_id)

    conn = await raw_connection(db_session)
    render = dict(await queries.find_stage_by_id(conn, id=stage_id))
    project = dict(await queries.find_project_by_id(conn, id=project_id))
    assert render["status"] == StageStatus.APPROVED
    assert project["status"] == ProjectStatus.DONE
    assert worker._queue.empty()
