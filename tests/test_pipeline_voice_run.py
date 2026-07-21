import json

import pytest

from app.auth.security import hash_password
from app.constants import (
    AssetKind,
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
from app.utils import storage
from app.utils.errors import AppError
from app.utils.time import now_local

_SCRIPT = {
    "title": "바다 거북",
    "hook": "훅",
    "scenes": [{"index": 1, "narration": "첫 문장.", "on_screen": "a"}],
    "estimated_duration_sec": 30,
}


async def _seed(session, email: str):
    """script(승인됨) + voice(대기) 단계를 가진 프로젝트를 만든다."""
    conn = await raw_connection(session)
    now = now_local()
    user = User(email=email, password_hash=hash_password("pw12345"),
                role=UserRole.MEMBER, status=UserStatus.ACTIVE)
    session.add(user)
    await session.commit()
    await session.refresh(user)

    project_id = await queries.insert_project(
        conn, owner_id=user.id, title="t", topic="주제",
        status=ProjectStatus.DRAFT, current_stage=StageName.VOICE, settings=json.dumps({}),
        created_at=now, updated_at=now, created_by=user.id, updated_by=user.id,
    )
    await queries.insert_stage(
        conn, project_id=project_id, name=StageName.SCRIPT, provider="fake",
        status=StageStatus.APPROVED, output=json.dumps(_SCRIPT), error=None, attempt=0,
        started_at=None, finished_at=None,
        created_at=now, updated_at=now, created_by=user.id, updated_by=user.id,
    )
    await queries.insert_stage(
        conn, project_id=project_id, name=StageName.VOICE, provider="fake",
        status=StageStatus.PENDING, output=json.dumps({}), error=None, attempt=0,
        started_at=None, finished_at=None,
        created_at=now, updated_at=now, created_by=user.id, updated_by=user.id,
    )
    await session.commit()
    project = pipeline.decode_stage(dict(await queries.find_project_by_id(conn, id=project_id)))
    voice = pipeline.decode_stage(
        dict(await queries.find_stage(conn, project_id=project_id, name=StageName.VOICE))
    )
    return user.id, project, voice


@pytest.mark.asyncio
async def test_run_voice_records_asset_and_uses_script_input(db_session, monkeypatch, tmp_path):
    monkeypatch.setattr(storage, "_root", lambda: tmp_path)
    actor, project, voice = await _seed(db_session, "voice-run@example.com")

    updated = await pipeline.run_stage(db_session, project, voice, actor_id=actor)
    assert updated["status"] == StageStatus.NEEDS_REVIEW
    # script의 나레이션이 실제로 전달됐다
    assert updated["output"]["chars"] == len("첫 문장.")

    conn = await raw_connection(db_session)
    assets = [dict(r) async for r in queries.list_assets_by_stage(conn, stage_id=voice["id"])]
    assert len(assets) == 1
    assert assets[0]["kind"] == AssetKind.AUDIO
    assert assets[0]["path"] == f"projects/{project['id']}/voice/voice.mp3"
    assert (tmp_path / assets[0]["path"]).exists()


@pytest.mark.asyncio
async def test_rerun_replaces_previous_asset(db_session, monkeypatch, tmp_path):
    monkeypatch.setattr(storage, "_root", lambda: tmp_path)
    actor, project, voice = await _seed(db_session, "voice-replace@example.com")

    await pipeline.run_stage(db_session, project, voice, actor_id=actor)
    conn = await raw_connection(db_session)
    first = [dict(r) async for r in queries.list_assets_by_stage(conn, stage_id=voice["id"])]

    # 재생성 → 다시 실행 (attempt가 올라가고 asset은 교체돼야 한다)
    reloaded = pipeline.decode_stage(
        dict(await queries.find_stage(conn, project_id=project["id"], name=StageName.VOICE))
    )
    await pipeline.regenerate_stage(db_session, project, reloaded, actor_id=actor)

    after = [dict(r) async for r in queries.list_assets_by_stage(conn, stage_id=voice["id"])]
    assert len(after) == 1  # 누적되지 않고 교체
    assert after[0]["id"] != first[0]["id"]
    assert (tmp_path / after[0]["path"]).exists()  # 교체 후에도 실제 파일이 있어야 한다


@pytest.mark.asyncio
async def test_run_failure_yields_stage_neutral_message(db_session, monkeypatch, tmp_path):
    monkeypatch.setattr(storage, "_root", lambda: tmp_path)
    from app.providers.voice.fake import FakeVoice

    async def _boom(self, ctx):
        raise RuntimeError("boom")

    monkeypatch.setattr(FakeVoice, "run", _boom)
    actor, project, voice = await _seed(db_session, "voice-fail@example.com")

    updated = await pipeline.run_stage(db_session, project, voice, actor_id=actor)
    assert updated["status"] == StageStatus.FAILED
    assert updated["error"] == "실행 중 오류가 발생했습니다. 잠시 후 다시 시도해 주세요."


@pytest.mark.asyncio
async def test_run_stage_rejects_when_already_running(db_session, monkeypatch, tmp_path):
    """[실행]을 두 번 빠르게 누른 상황(I2)의 절반: 이미 RUNNING인 단계는 재실행할 수 없다."""
    monkeypatch.setattr(storage, "_root", lambda: tmp_path)
    actor, project, voice = await _seed(db_session, "voice-already-running@example.com")

    conn = await raw_connection(db_session)
    now = now_local()
    await queries.update_stage_status(
        conn, id=voice["id"], status=StageStatus.RUNNING, updated_at=now, updated_by=actor
    )
    await db_session.commit()
    reloaded = pipeline.decode_stage(
        dict(await queries.find_stage(conn, project_id=project["id"], name=StageName.VOICE))
    )

    with pytest.raises(AppError) as exc:
        await pipeline.run_stage(db_session, project, reloaded, actor_id=actor)
    assert exc.value.status_code == 409


@pytest.mark.asyncio
async def test_run_persists_running_status_mid_flight(db_session, monkeypatch, tmp_path):
    """I2: run_stage가 provider를 돌리기 전에 DB에 RUNNING을 커밋 없이도 기록하는지 확인한다.

    db_session은 raw_connection()이 항상 같은 커넥션/트랜잭션을 돌려주므로(conftest의
    SAVEPOINT 격리 패턴), provider.run 안에서 같은 세션으로 stage를 다시 읽으면
    run_stage가 아직 커밋하지 않은 RUNNING을 그대로 볼 수 있다(같은 트랜잭션 내
    read-your-own-writes) — 별도 커넥션/스레드 없이 결정적으로 검증 가능하다.
    """
    monkeypatch.setattr(storage, "_root", lambda: tmp_path)
    from app.providers.voice.fake import FakeVoice

    actor, project, voice = await _seed(db_session, "voice-running-midflight@example.com")

    original_run = FakeVoice.run
    seen_status = {}

    async def _spy_run(self, ctx):
        conn = await raw_connection(db_session)
        mid = await queries.find_stage(conn, project_id=project["id"], name=StageName.VOICE)
        seen_status["status"] = mid["status"]
        return await original_run(self, ctx)

    monkeypatch.setattr(FakeVoice, "run", _spy_run)

    updated = await pipeline.run_stage(db_session, project, voice, actor_id=actor)
    assert seen_status["status"] == StageStatus.RUNNING
    assert updated["status"] == StageStatus.NEEDS_REVIEW


@pytest.mark.asyncio
async def test_previous_context_carries_voice_audio_to_next_stage(db_session, monkeypatch, tmp_path):
    """voice가 만든 mp3가 다음 단계(captions)의 input_assets로 전달되는지."""
    monkeypatch.setattr(storage, "_root", lambda: tmp_path)
    actor, project, voice = await _seed(db_session, "voice-assets@example.com")
    await pipeline.run_stage(db_session, project, voice, actor_id=actor)

    conn = await raw_connection(db_session)
    _, assets = await pipeline._previous_context(conn, project["id"], StageName.CAPTIONS)
    audio = [a for a in assets["voice"] if a["kind"] == AssetKind.AUDIO]
    assert len(audio) == 1
    assert audio[0]["path"] == f"projects/{project['id']}/voice/voice.mp3"
    # meta는 jsonb라 asyncpg가 문자열로 준다 — dict로 디코드돼야 한다
    assert audio[0]["meta"]["size_bytes"] > 0
