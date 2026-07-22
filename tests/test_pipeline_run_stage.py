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
    await pipeline.regenerate_stage(db_session, ran, actor_id=actor)
    conn = await raw_connection(db_session)
    regen = pipeline.decode_stage(await queries.find_stage_by_id(conn, id=stage["id"]))
    assert regen["attempt"] == 1
    assert regen["status"] == StageStatus.QUEUED


@pytest.mark.asyncio
async def test_regenerate_stage_rejects_when_stage_already_running(db_session):
    """[재생성] 더블클릭 레이스(I4): 두 번째 regenerate_stage는 진행 중인 RUNNING을 덮어쓰면 안 된다.

    시나리오: 두 요청 A/B가 같은 NEEDS_REVIEW를 읽고 can_transition 게이트를 통과한다(여기서는
    A가 이미 통과해 QUEUED→RUNNING까지 간 뒤, B가 뒤늦게 도착한 상황을 재현한다). 상태 술어 없는
    UPDATE였다면 B가 RUNNING을 PENDING으로 덮어쓰고 뒤이은 queue_stage가 성공해 202를 돌려줬을
    것이다 — 그러면 워커 두 개가 같은 단계를 동시에 실행해 _replace_assets가 서로의 산출물을 지운다.
    """
    actor, project, stage = await _seed_project_and_stage(db_session)
    ran = await _run_to_completion(db_session, project, stage, actor)  # NEEDS_REVIEW

    # A: 정상적으로 재생성 요청 → NEEDS_REVIEW → PENDING → QUEUED
    await pipeline.regenerate_stage(db_session, ran, actor_id=actor)
    conn = await raw_connection(db_session)
    queued = pipeline.decode_stage(await queries.find_stage_by_id(conn, id=stage["id"]))
    assert queued["status"] == StageStatus.QUEUED

    # 워커가 A를 집어 RUNNING으로 선점했다고 가정한다.
    claimed = await pipeline.claim_stage(db_session, stage["id"], actor_id=actor)
    assert claimed is not None
    assert claimed["status"] == StageStatus.RUNNING

    # B: 낡은 NEEDS_REVIEW 스냅숏(ran)을 들고 뒤늦게 도착 — can_transition 게이트는 통과하지만
    # DB의 CAS(WHERE status = 'NEEDS_REVIEW')가 실제 상태(RUNNING)와 안 맞아 거절해야 한다.
    with pytest.raises(AppError) as exc_info:
        await pipeline.regenerate_stage(db_session, ran, actor_id=actor)
    assert exc_info.value.status_code == 409
    assert exc_info.value.code == "STAGE_CONFLICT"

    still_running = pipeline.decode_stage(await queries.find_stage_by_id(conn, id=stage["id"]))
    assert still_running["status"] == StageStatus.RUNNING


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
