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
