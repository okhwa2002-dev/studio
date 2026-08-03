"""정리 잡 — 만료 refresh token 삭제 + 보관 기간 지난 프로젝트 완전 삭제.

주기 루프는 돌리지 않는다(24시간을 기다릴 수 없다). run_once를 직접 부른다.
"""

import json
from contextlib import asynccontextmanager
from datetime import timedelta

import pytest

from app.auth.security import hash_password
from app.constants import AuditAction, ProjectStatus, StageName, StageStatus, UserRole, UserStatus
from app.core import cleanup
from app.db import raw_connection
from app.models.audit_log import AuditLog
from app.models.user import User
from app.queries import queries
from app.utils import storage
from app.utils.time import now_local


def _factory(session):
    """잡이 자체 세션 대신 테스트 세션을 쓰게 한다 — SAVEPOINT 격리 유지."""

    @asynccontextmanager
    async def _make():
        yield session

    return _make


@pytest.fixture(autouse=True)
def storage_root(monkeypatch, tmp_path):
    """파일 삭제를 실제로 검증하되 프로젝트의 storage/를 건드리지 않는다."""
    monkeypatch.setattr(storage, "_root", lambda: tmp_path)
    return tmp_path


async def _add_user(session, email: str) -> User:
    user = User(
        email=email,
        password_hash=hash_password("pw12345"),
        role=UserRole.MEMBER,
        status=UserStatus.ACTIVE,
    )
    session.add(user)
    await session.commit()
    await session.refresh(user)
    return user


async def _add_project(session, owner_id: int, *, deleted_at=None, title="t") -> int:
    """프로젝트 + script 단계 + asset 1건 + 파일을 만든다."""
    conn = await raw_connection(session)
    now = now_local()
    project_id = await queries.insert_project(
        conn, owner_id=owner_id, title=title, topic="주제",
        status=ProjectStatus.DRAFT, current_stage=StageName.SCRIPT,
        settings=json.dumps({}), created_at=now, updated_at=now,
        created_by=owner_id, updated_by=owner_id,
    )
    stage_id = await queries.insert_stage(
        conn, project_id=project_id, name=StageName.VOICE, provider="fake",
        status=StageStatus.APPROVED, output=json.dumps({}), error=None, attempt=1,
        started_at=None, finished_at=None, created_at=now, updated_at=now,
        created_by=owner_id, updated_by=owner_id,
    )
    rel = f"projects/{project_id}/voice/voice.mp3"
    storage.write_bytes(rel, b"audio")
    await queries.insert_asset(
        conn, stage_id=stage_id, kind="audio", path=rel, meta=json.dumps({}),
        created_at=now, updated_at=now, created_by=owner_id, updated_by=owner_id,
    )
    # 스톡 소재처럼 asset으로 기록되지 않는 파일도 함께 둔다.
    storage.write_bytes(f"projects/{project_id}/render/sources/scene1.mp4", b"clip")

    if deleted_at is not None:
        await queries.soft_delete_project(
            conn, id=project_id, deleted_at=deleted_at, deleted_by=owner_id
        )
    await session.commit()
    return project_id


async def _project_exists(session, project_id: int) -> bool:
    conn = await raw_connection(session)
    row = await conn.fetchrow("SELECT id FROM projects WHERE id = $1", project_id)
    return row is not None


async def _count_children(session, project_id: int) -> tuple[int, int]:
    conn = await raw_connection(session)
    stages = await conn.fetchval("SELECT COUNT(*) FROM stages WHERE project_id = $1", project_id)
    assets = await conn.fetchval(
        "SELECT COUNT(*) FROM assets WHERE stage_id IN "
        "(SELECT id FROM stages WHERE project_id = $1)",
        project_id,
    )
    return stages, assets


async def _add_refresh_token(session, user_id: int, *, token_hash: str, expires_at, revoked=False):
    conn = await raw_connection(session)
    now = now_local()
    token_id = await queries.insert_refresh_token(
        conn, user_id=user_id, token_hash=token_hash,
        expires_at=expires_at, created_at=now, updated_at=now,
    )
    if revoked:
        await queries.revoke_by_id(conn, id=token_id, revoked_at=now, updated_at=now)
    await session.commit()
    return token_id


async def _token_exists(session, token_hash: str) -> bool:
    conn = await raw_connection(session)
    row = await conn.fetchrow(
        "SELECT id FROM refresh_tokens WHERE token_hash = $1", token_hash
    )
    return row is not None


# ─── refresh token ───


async def test_expired_token_is_deleted(db_session):
    user = await _add_user(db_session, "cl-exp@example.com")
    await _add_refresh_token(
        db_session, user.id, token_hash="expired", expires_at=now_local() - timedelta(days=1)
    )

    await cleanup.run_once(_factory(db_session))

    assert not await _token_exists(db_session, "expired")


async def test_revoked_but_unexpired_token_is_kept(db_session):
    """탈취 경보가 계속 동작해야 한다.

    refresh()는 폐기된 토큰이 재사용되면 그 사용자의 모든 세션을 끊는다. 폐기 토큰을
    만료 전에 지우면 재사용이 '없는 토큰'으로 보여 평범한 401이 나가고 경보가 죽는다.
    """
    user = await _add_user(db_session, "cl-revoked@example.com")
    await _add_refresh_token(
        db_session, user.id, token_hash="revoked-live",
        expires_at=now_local() + timedelta(days=7), revoked=True,
    )

    await cleanup.run_once(_factory(db_session))

    assert await _token_exists(db_session, "revoked-live")


async def test_live_token_is_kept(db_session):
    user = await _add_user(db_session, "cl-live@example.com")
    await _add_refresh_token(
        db_session, user.id, token_hash="live", expires_at=now_local() + timedelta(days=7)
    )

    await cleanup.run_once(_factory(db_session))

    assert await _token_exists(db_session, "live")


# ─── 프로젝트 완전 삭제 ───


async def test_purges_project_past_retention(db_session, storage_root):
    user = await _add_user(db_session, "cl-old@example.com")
    old = now_local() - timedelta(days=cleanup.PROJECT_RETENTION_DAYS + 1)
    project_id = await _add_project(db_session, user.id, deleted_at=old)

    await cleanup.run_once(_factory(db_session))

    assert not await _project_exists(db_session, project_id)
    assert await _count_children(db_session, project_id) == (0, 0)


async def test_purge_removes_files_including_unrecorded_ones(db_session, storage_root):
    """asset으로 기록되지 않은 스톡 소재까지 서브트리 전체가 사라진다."""
    user = await _add_user(db_session, "cl-files@example.com")
    old = now_local() - timedelta(days=cleanup.PROJECT_RETENTION_DAYS + 1)
    project_id = await _add_project(db_session, user.id, deleted_at=old)
    assert (storage_root / f"projects/{project_id}/render/sources/scene1.mp4").exists()

    await cleanup.run_once(_factory(db_session))

    assert not (storage_root / f"projects/{project_id}").exists()


async def test_keeps_project_within_retention(db_session, storage_root):
    user = await _add_user(db_session, "cl-recent@example.com")
    recent = now_local() - timedelta(days=cleanup.PROJECT_RETENTION_DAYS - 1)
    project_id = await _add_project(db_session, user.id, deleted_at=recent)

    await cleanup.run_once(_factory(db_session))

    assert await _project_exists(db_session, project_id)
    assert (storage_root / f"projects/{project_id}").exists()


async def test_keeps_project_that_was_never_deleted(db_session, storage_root):
    user = await _add_user(db_session, "cl-alive@example.com")
    project_id = await _add_project(db_session, user.id)  # deleted_at NULL

    await cleanup.run_once(_factory(db_session))

    assert await _project_exists(db_session, project_id)
    assert (storage_root / f"projects/{project_id}").exists()


async def test_purge_leaves_other_projects_untouched(db_session, storage_root):
    user = await _add_user(db_session, "cl-mixed@example.com")
    old = now_local() - timedelta(days=cleanup.PROJECT_RETENTION_DAYS + 1)
    purged = await _add_project(db_session, user.id, deleted_at=old)
    kept = await _add_project(db_session, user.id)

    await cleanup.run_once(_factory(db_session))

    assert not await _project_exists(db_session, purged)
    assert await _project_exists(db_session, kept)
    assert await _count_children(db_session, kept) == (1, 1)
    assert (storage_root / f"projects/{kept}/voice/voice.mp3").exists()


async def test_purge_is_recorded_before_the_commit(db_session, storage_root):
    """완전 삭제가 PROJECT_PURGE로 남고, 그 기록이 실제로 커밋되는지 본다.

    _purge_project는 마지막에 한 번만 커밋한다. audit.record는 커밋하지 않으므로
    호출이 그 커밋보다 뒤로 밀리면 행이 조용히 사라진다 — rollback() 뒤에도 남는지로
    판별한다(test_core_audit.py::test_record_failure_survives_rollback과 같은 패턴).

    제목은 행이 지워진 뒤에는 읽을 수 없다. list_purgeable_projects가 미리 읽어
    넘겨주지 않으면 target_label이 비고, 그러면 이 단언이 깨진다.
    """
    user = await _add_user(db_session, "cl-purge-audit@example.com")
    old = now_local() - timedelta(days=cleanup.PROJECT_RETENTION_DAYS + 1)
    project_id = await _add_project(db_session, user.id, deleted_at=old, title="여행 브이로그")

    await cleanup.run_once(_factory(db_session))
    await db_session.rollback()

    conn = await raw_connection(db_session)
    rows = await conn.fetch(
        "SELECT * FROM audit_logs WHERE action = $1 ORDER BY id", AuditAction.PROJECT_PURGE
    )
    assert len(rows) == 1
    row = rows[0]
    assert row["target_type"] == "PROJECT"
    assert row["target_id"] == project_id
    assert row["target_label"] == "여행 브이로그"
    assert row["summary"] == "보관 기간 경과로 완전 삭제"
    assert row["success_yn"] == "Y"
    # 사람이 아니라 잡이 주체다 — 행위자·호출 정보가 전부 비어 있다(설계 2-4).
    assert row["actor_id"] is None
    assert row["actor_email"] is None
    assert row["http_method"] is None
    assert row["http_path"] is None
    assert row["actor_ip"] is None


async def test_purge_records_nothing_for_projects_within_retention(db_session, storage_root):
    """지우지 않은 프로젝트에는 기록도 없어야 한다.

    여기서 rollback()을 쓰면 안 된다 — "기록이 없다"를 확인하는 테스트가 스스로
    증거를 지워 무조건 통과하게 된다.
    """
    user = await _add_user(db_session, "cl-nopurge-audit@example.com")
    recent = now_local() - timedelta(days=cleanup.PROJECT_RETENTION_DAYS - 1)
    await _add_project(db_session, user.id, deleted_at=recent)

    await cleanup.run_once(_factory(db_session))

    conn = await raw_connection(db_session)
    rows = await conn.fetch("SELECT id FROM audit_logs WHERE action = $1", AuditAction.PROJECT_PURGE)
    assert rows == []


async def test_run_once_is_idempotent(db_session, storage_root):
    user = await _add_user(db_session, "cl-twice@example.com")
    old = now_local() - timedelta(days=cleanup.PROJECT_RETENTION_DAYS + 1)
    await _add_project(db_session, user.id, deleted_at=old)

    await cleanup.run_once(_factory(db_session))
    await cleanup.run_once(_factory(db_session))  # 두 번째도 예외 없이 통과


async def test_run_once_on_empty_db_does_nothing(db_session):
    await cleanup.run_once(_factory(db_session))


# ─── 감사 로그 보관 정리 ───


async def test_audit_logs_older_than_retention_are_purged(db_session):
    old = AuditLog(
        action=AuditAction.LOGIN_SUCCESS,
        created_at=now_local() - timedelta(days=cleanup.AUDIT_RETENTION_DAYS + 1),
    )
    fresh = AuditLog(
        action=AuditAction.LOGIN_SUCCESS,
        created_at=now_local() - timedelta(days=cleanup.AUDIT_RETENTION_DAYS - 1),
    )
    db_session.add(old)
    db_session.add(fresh)
    await db_session.commit()

    await cleanup.run_once(_factory(db_session))

    conn = await raw_connection(db_session)
    remaining = await conn.fetch("SELECT id FROM audit_logs")
    assert [r["id"] for r in remaining] == [fresh.id]


# ─── 재설정 코드 정리 ───


async def _add_reset_code(session, user_id: int, *, code: str, expires_at, consumed=False):
    conn = await raw_connection(session)
    now = now_local()
    code_id = await queries.insert_reset_code(
        conn, user_id=user_id, code=code, expires_at=expires_at,
        created_at=now, updated_at=now,
    )
    if consumed:
        await queries.consume_reset_code(conn, id=code_id, consumed_at=now, updated_at=now)
    await session.commit()
    return code_id


async def _reset_code_exists(session, code: str) -> bool:
    conn = await raw_connection(session)
    row = await conn.fetchrow("SELECT id FROM password_reset_codes WHERE code = $1", code)
    return row is not None


async def test_expired_reset_code_is_deleted(db_session):
    user = await _add_user(db_session, "cl-code-exp@example.com")
    await _add_reset_code(
        db_session, user.id, code="111111", expires_at=now_local() - timedelta(minutes=1)
    )

    await cleanup.run_once(_factory(db_session))

    assert not await _reset_code_exists(db_session, "111111")


async def test_live_reset_code_is_kept(db_session):
    """진행 중인 재설정을 잡이 끊으면 안 된다."""
    user = await _add_user(db_session, "cl-code-live@example.com")
    await _add_reset_code(
        db_session, user.id, code="222222", expires_at=now_local() + timedelta(minutes=10)
    )

    await cleanup.run_once(_factory(db_session))

    assert await _reset_code_exists(db_session, "222222")


async def test_consumed_but_unexpired_reset_code_is_kept(db_session):
    """삭제 조건은 expires_at 하나다.

    소비 여부를 조건에 넣지 않는 이유는 코드 TTL이 10분이라 소비된 코드도 곧 만료로
    걸리기 때문이다(설계 2.1). 조건이 늘면 "왜 이 행이 남아 있나"를 만료 시각 하나로
    설명할 수 없게 된다 — 이 테스트가 그 단순함을 고정한다.
    """
    user = await _add_user(db_session, "cl-code-used@example.com")
    await _add_reset_code(
        db_session, user.id, code="333333",
        expires_at=now_local() + timedelta(minutes=10), consumed=True,
    )

    await cleanup.run_once(_factory(db_session))

    assert await _reset_code_exists(db_session, "333333")
