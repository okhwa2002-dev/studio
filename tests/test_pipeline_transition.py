import json

import pytest

from app.auth.security import hash_password
from app.constants import (
    ProjectStatus,
    StageName,
    StageStatus,
    UserRole,
    UserStatus,
)
from app.core import pipeline
from app.db import raw_connection
from app.models.user import User
from app.queries import queries
from app.utils.time import now_local


async def _seed_script_needs_review(session, email: str):
    conn = await raw_connection(session)
    now = now_local()
    user = User(email=email, password_hash=hash_password("pw12345"),
                role=UserRole.MEMBER, status=UserStatus.ACTIVE)
    session.add(user)
    await session.commit()
    await session.refresh(user)

    project_id = await queries.insert_project(
        conn, owner_id=user.id, title="t", topic="주제",
        status=ProjectStatus.DRAFT, current_stage=StageName.SCRIPT, settings=json.dumps({}),
        created_at=now, updated_at=now, created_by=user.id, updated_by=user.id,
    )
    await queries.insert_stage(
        conn, project_id=project_id, name=StageName.SCRIPT, provider="fake",
        status=StageStatus.NEEDS_REVIEW, output=json.dumps({"scenes": []}), error=None, attempt=0,
        started_at=None, finished_at=None,
        created_at=now, updated_at=now, created_by=user.id, updated_by=user.id,
    )
    await session.commit()
    project = pipeline.decode_stage(dict(await queries.find_project_by_id(conn, id=project_id)))
    stage = pipeline.decode_stage(
        dict(await queries.find_stage(conn, project_id=project_id, name=StageName.SCRIPT))
    )
    return user.id, project, stage


@pytest.mark.asyncio
async def test_approving_script_registers_voice_pending(db_session):
    actor, project, script = await _seed_script_needs_review(db_session, "trans1@example.com")
    await pipeline.approve_stage(db_session, project, script, actor_id=actor)

    conn = await raw_connection(db_session)
    voice = await queries.find_stage(conn, project_id=project["id"], name=StageName.VOICE)
    assert voice is not None, "script 승인 시 voice 단계가 등록돼야 한다"
    assert voice["status"] == StageStatus.PENDING

    updated_project = dict(await queries.find_project_by_id(conn, id=project["id"]))
    assert updated_project["current_stage"] == StageName.VOICE
    # 아직 마지막 단계가 아니므로 DONE이 아니다
    assert updated_project["status"] != ProjectStatus.DONE


@pytest.mark.asyncio
async def test_approving_last_stage_marks_project_done(db_session):
    actor, project, script = await _seed_script_needs_review(db_session, "trans2@example.com")
    await pipeline.approve_stage(db_session, project, script, actor_id=actor)

    conn = await raw_connection(db_session)
    voice = pipeline.decode_stage(
        dict(await queries.find_stage(conn, project_id=project["id"], name=StageName.VOICE))
    )
    # voice를 검토 상태로 만든 뒤 승인 → 마지막 구현 단계이므로 프로젝트 DONE
    await queries.update_stage_status(
        conn, id=voice["id"], status=StageStatus.NEEDS_REVIEW,
        updated_at=now_local(), updated_by=actor,
    )
    await db_session.commit()
    voice["status"] = StageStatus.NEEDS_REVIEW
    await pipeline.approve_stage(db_session, project, voice, actor_id=actor)

    updated_project = dict(await queries.find_project_by_id(conn, id=project["id"]))
    assert updated_project["status"] == ProjectStatus.DONE


@pytest.mark.asyncio
async def test_reapproving_does_not_duplicate_next_stage(db_session):
    actor, project, script = await _seed_script_needs_review(db_session, "trans3@example.com")
    await pipeline.approve_stage(db_session, project, script, actor_id=actor)

    conn = await raw_connection(db_session)
    # script를 다시 검토 상태로 되돌린 뒤 또 승인해도 voice가 중복 생성되면 안 된다
    await queries.update_stage_status(
        conn, id=script["id"], status=StageStatus.NEEDS_REVIEW,
        updated_at=now_local(), updated_by=actor,
    )
    await db_session.commit()
    script["status"] = StageStatus.NEEDS_REVIEW
    await pipeline.approve_stage(db_session, project, script, actor_id=actor)

    stages = [dict(r) async for r in queries.list_stages_by_project(conn, project_id=project["id"])]
    assert [s["name"] for s in stages].count(StageName.VOICE) == 1


@pytest.mark.asyncio
async def test_previous_outputs_excludes_current_and_later_stages(db_session):
    """STAGE_ORDER에 두 단계가 있을 때 _previous_outputs의 break가 실제로 동작하는지 확인.

    script(첫 단계) 기준으로는 앞 단계가 없으므로 inputs가 비어 있어야 하고,
    voice(다음 단계) 기준으로는 script 산출물만 포함돼야 한다(자기 자신·이후 단계 제외).
    """
    actor, project, script = await _seed_script_needs_review(db_session, "trans4@example.com")
    conn = await raw_connection(db_session)

    script_inputs = await pipeline._previous_outputs(conn, project["id"], StageName.SCRIPT)
    assert script_inputs == {}

    voice_inputs = await pipeline._previous_outputs(conn, project["id"], StageName.VOICE)
    assert voice_inputs == {"script": {"scenes": []}}
