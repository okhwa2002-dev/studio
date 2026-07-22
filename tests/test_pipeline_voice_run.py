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


async def _run_to_completion(session, project, stage, actor):
    """queue → claim → run 전체를 밟아 단계를 완료시킨다."""
    assert await pipeline.queue_stage(session, stage["id"], actor_id=actor)
    claimed = await pipeline.claim_stage(session, stage["id"], actor_id=actor)
    assert claimed is not None
    return await pipeline.run_claimed_stage(session, project, claimed, actor_id=actor)


async def _claim_and_run(session, project, stage, actor):
    """이미 QUEUED인 단계(예: regenerate_stage 직후)를 claim→run으로 마저 완료시킨다."""
    claimed = await pipeline.claim_stage(session, stage["id"], actor_id=actor)
    assert claimed is not None
    return await pipeline.run_claimed_stage(session, project, claimed, actor_id=actor)


@pytest.mark.asyncio
async def test_run_voice_records_asset_and_uses_script_input(db_session, monkeypatch, tmp_path):
    monkeypatch.setattr(storage, "_root", lambda: tmp_path)
    actor, project, voice = await _seed(db_session, "voice-run@example.com")

    updated = await _run_to_completion(db_session, project, voice, actor)
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

    await _run_to_completion(db_session, project, voice, actor)
    conn = await raw_connection(db_session)
    first = [dict(r) async for r in queries.list_assets_by_stage(conn, stage_id=voice["id"])]

    # 재생성(PENDING → QUEUED) → 워커 대신 claim+run으로 마저 돌린다 (attempt가 올라가고 asset은 교체돼야 한다)
    reloaded = pipeline.decode_stage(
        dict(await queries.find_stage(conn, project_id=project["id"], name=StageName.VOICE))
    )
    await pipeline.regenerate_stage(db_session, reloaded, actor_id=actor)
    requeued = pipeline.decode_stage(
        dict(await queries.find_stage(conn, project_id=project["id"], name=StageName.VOICE))
    )
    await _claim_and_run(db_session, project, requeued, actor)

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

    updated = await _run_to_completion(db_session, project, voice, actor)
    assert updated["status"] == StageStatus.FAILED
    assert updated["error"] == "실행 중 오류가 발생했습니다. 잠시 후 다시 시도해 주세요."


@pytest.mark.asyncio
async def test_queue_stage_rejects_when_already_running(db_session, monkeypatch, tmp_path):
    """[실행]을 두 번 빠르게 누른 상황(I2)의 절반: 이미 RUNNING인 단계는 다시 큐에 넣을 수 없다.

    이전에는 run_stage(단일 함수)가 RUNNING인 단계에 대해 AppError(409)를 던졌다. 지금은
    실행이 queue_stage(PENDING/FAILED→QUEUED)와 claim_stage(QUEUED→RUNNING)로 나뉘었고,
    둘 다 CAS 기반이라 조건이 안 맞으면 예외 대신 False/None을 돌려준다. 등가 단언은
    "RUNNING인 단계는 queue_stage가 거절한다"이다.
    """
    monkeypatch.setattr(storage, "_root", lambda: tmp_path)
    actor, project, voice = await _seed(db_session, "voice-already-running@example.com")

    conn = await raw_connection(db_session)
    now = now_local()
    await queries.update_stage_status(
        conn, id=voice["id"], status=StageStatus.RUNNING, updated_at=now, updated_by=actor
    )
    await db_session.commit()

    assert await pipeline.queue_stage(db_session, voice["id"], actor_id=actor) is False


@pytest.mark.asyncio
async def test_run_one_commits_running_before_provider_runs(db_session, monkeypatch, tmp_path):
    """I3(리뷰): StageWorker.run_one이 claim_stage를 커밋한 뒤에야 provider를 실행하는지 실제로 고정한다.

    이전 버전은 테스트가 직접 queue→claim→commit→재조회 순서를 손으로 흉내 냈을 뿐이라,
    worker.run_one 안의 실제 커밋(app/core/worker.py:100, claim 직후 session.commit())을
    지워도 이 테스트는 그대로 통과했다(task-7-review.md I-3).

    처음에는 "provider 실행 시점에 DB를 다시 읽어 RUNNING인지 확인"하는 스파이로 다시 썼지만,
    실제로 commit()을 지우고 돌려본 결과 그 버전도 여전히 통과한다는 걸 확인했다 — 워커와
    스파이가 **같은 세션/커넥션**을 쓰는 이 테스트 픽스처(SAVEPOINT 격리)에서는, 커밋 여부와
    무관하게 같은 트랜잭션 안의 쓰기가 곧바로 자기 자신에게는 보이기 때문이다(read-your-own-writes는
    커밋과 무관). 즉 "DB를 다시 읽기"로는 커밋 유무를 구분할 수 없다 — I-1이 지적한 것과 같은
    종류의 픽스처 한계다.

    그래서 실제로 규레션을 잡는 방식으로 바꿨다: `session.commit`과 `FakeVoice.run` 양쪽에
    호출 순서를 기록하는 스파이를 심고, **첫 commit 호출이 provider.run 호출보다 먼저 일어났는지**를
    직접 검증한다. commit()을 지우거나 run_claimed_stage 뒤로 옮기면 provider.run이 먼저(또는
    커밋 없이) 기록되어 이 단언이 깨진다 — 실제로 worker.py의 커밋 줄을 주석 처리해 이 테스트가
    실패하는 것을 확인했다(회귀 검증, task-7-report.md 참고).
    """
    from contextlib import asynccontextmanager

    from app.core.worker import StageWorker
    from app.providers.voice.fake import FakeVoice

    monkeypatch.setattr(storage, "_root", lambda: tmp_path)
    actor, project, voice = await _seed(db_session, "voice-running-midflight@example.com")
    assert await pipeline.queue_stage(db_session, voice["id"], actor_id=actor)
    await db_session.commit()

    order: list[str] = []
    real_commit = db_session.commit
    real_run = FakeVoice.run

    async def _commit_spy():
        order.append("commit")
        await real_commit()

    async def _run_spy(self, ctx):
        order.append("provider_run")
        return await real_run(self, ctx)

    monkeypatch.setattr(db_session, "commit", _commit_spy)
    monkeypatch.setattr(FakeVoice, "run", _run_spy)

    @asynccontextmanager
    async def _factory():
        yield db_session

    await StageWorker(session_factory=_factory).run_one(voice["id"])

    # run_claimed_stage도 끝에 한 번 더 commit하므로 순서는 [commit, provider_run, commit]이
    # 될 것이다 — 우리가 고정하려는 사실은 "첫 commit이 provider_run보다 앞선다"는 것뿐이다.
    assert order.index("commit") < order.index("provider_run"), (
        f"RUNNING 커밋이 provider 실행보다 뒤에(또는 없이) 일어났다: {order}"
    )

    conn = await raw_connection(db_session)
    final = await queries.find_stage(conn, project_id=project["id"], name=StageName.VOICE)
    assert final["status"] == StageStatus.NEEDS_REVIEW


@pytest.mark.asyncio
async def test_previous_context_carries_voice_audio_to_next_stage(db_session, monkeypatch, tmp_path):
    """voice가 만든 mp3가 다음 단계(captions)의 input_assets로 전달되는지."""
    monkeypatch.setattr(storage, "_root", lambda: tmp_path)
    actor, project, voice = await _seed(db_session, "voice-assets@example.com")
    await _run_to_completion(db_session, project, voice, actor)

    conn = await raw_connection(db_session)
    _, assets = await pipeline._previous_context(conn, project["id"], StageName.CAPTIONS)
    audio = [a for a in assets["voice"] if a["kind"] == AssetKind.AUDIO]
    assert len(audio) == 1
    assert audio[0]["path"] == f"projects/{project['id']}/voice/voice.mp3"
    # meta는 jsonb라 asyncpg가 문자열로 준다 — dict로 디코드돼야 한다
    assert audio[0]["meta"]["size_bytes"] > 0
