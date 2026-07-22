import json

import pytest

from app.constants import ProjectStatus, StageName, StageStatus
from app.core import pipeline
from app.db import raw_connection
from app.queries import queries
from app.utils.time import now_local


async def _seed_openai_stage(session, provider="openai"):
    conn = await raw_connection(session)
    now = now_local()
    from app.auth.security import hash_password
    from app.constants import UserRole, UserStatus
    from app.models.user import User

    user = User(email="valowner@example.com", password_hash=hash_password("pw12345"),
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
        conn, project_id=project_id, name=StageName.SCRIPT, provider=provider,
        status=StageStatus.PENDING, output=json.dumps({}), error=None, attempt=0,
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
async def test_run_stage_fails_friendly_when_openai_key_missing(db_session, monkeypatch):
    # OpenAIScript.validate가 참조하는 설정의 키를 비운다 → 실행 시 FAILED(친절 메시지), network 미접속
    monkeypatch.setattr(
        "app.providers.script.openai.get_settings",
        lambda: __import__("types").SimpleNamespace(openai_api_key=""),
    )
    actor, project, stage = await _seed_openai_stage(db_session)
    updated = await _run_to_completion(db_session, project, stage, actor)
    assert updated["status"] == StageStatus.FAILED
    assert updated["error"] == "OPENAI_API_KEY가 설정되지 않았습니다."


@pytest.mark.asyncio
async def test_run_stage_fails_friendly_when_claude_key_missing(db_session, monkeypatch):
    # ClaudeScript.validate가 참조하는 설정의 키를 비운다 → 실행 시 FAILED(친절 메시지), network 미접속
    monkeypatch.setattr(
        "app.providers.script.claude.get_settings",
        lambda: __import__("types").SimpleNamespace(anthropic_api_key=""),
    )
    actor, project, stage = await _seed_openai_stage(db_session, provider="claude")
    updated = await _run_to_completion(db_session, project, stage, actor)
    assert updated["status"] == StageStatus.FAILED
    assert updated["error"] == "ANTHROPIC_API_KEY가 설정되지 않았습니다."


@pytest.mark.asyncio
async def test_run_stage_fails_cleanly_when_provider_unknown(db_session):
    # SCRIPT_PROVIDER 오타 등으로 존재하지 않는 provider가 저장된 경우 500이 아니라 FAILED로 흡수돼야 한다(I-1).
    actor, project, stage = await _seed_openai_stage(db_session, provider="nope")
    updated = await _run_to_completion(db_session, project, stage, actor)
    assert updated["status"] == StageStatus.FAILED
    assert "provider를 찾을 수 없습니다" in updated["error"]
