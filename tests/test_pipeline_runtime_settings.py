import json

from app.auth.security import hash_password
from app.constants import UserRole, UserStatus
from app.db import raw_connection
from app.models.user import User
from app.queries import queries
from app.runtime_settings import invalidate_runtime_settings
from app.utils.time import now_local


async def _admin(client, db_session, email: str) -> User:
    user = User(
        email=email,
        password_hash=hash_password("pw12345678"),
        role=UserRole.ADMIN,
        status=UserStatus.ACTIVE,
        name="관리자",
    )
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    resp = await client.post(
        "/api/auth/login", json={"email": email, "password": "pw12345678"}
    )
    assert resp.status_code == 200
    return user


async def _override(db_session, key: str, value) -> None:
    conn = await raw_connection(db_session)
    await queries.upsert_setting(
        conn, key=key, value=json.dumps(value), now=now_local(), actor_id=None
    )
    invalidate_runtime_settings()


async def test_new_project_uses_runtime_script_provider(client, db_session):
    await _admin(client, db_session, "pipe-new@example.com")
    await _override(db_session, "script_provider", "claude")

    resp = await client.post(
        "/api/projects", json={"title": "테스트", "topic": "주제", "auto_run": False}
    )
    assert resp.status_code == 201
    script = next(s for s in resp.json()["stages"] if s["name"] == "script")
    assert script["provider"] == "claude"


async def test_existing_stage_keeps_its_provider_when_setting_changes(client, db_session):
    """이미 만들어진 단계는 스냅샷이다 — 설정을 바꿔도 따라 바뀌지 않는다."""
    await _admin(client, db_session, "pipe-snap@example.com")

    created = await client.post(
        "/api/projects", json={"title": "테스트", "topic": "주제", "auto_run": False}
    )
    project_id = created.json()["project"]["id"]
    assert next(
        s for s in created.json()["stages"] if s["name"] == "script"
    )["provider"] == "fake"

    await _override(db_session, "script_provider", "claude")

    detail = await client.get(f"/api/projects/{project_id}")
    script = next(s for s in detail.json()["stages"] if s["name"] == "script")
    assert script["provider"] == "fake"


async def test_stage_context_receives_runtime_settings(client, db_session, monkeypatch):
    """provider는 DB를 읽지 않는다 — 파이프라인이 ctx.settings에 실어 보낸다.

    HTTP의 .../run은 워커에 큐잉만 하고 202를 돌려주므로 실행 완료를 기다릴 수 없다.
    tests/test_pipeline_run_stage.py와 같이 파이프라인을 직접 구동한다.
    """
    from app.core import pipeline
    from app.providers.base import StageResult
    from app.providers.script.fake import FakeScript

    seen: dict = {}

    async def _capture(self, ctx):
        seen.update(ctx.settings)
        return StageResult(output={"scenes": []})

    monkeypatch.setattr(FakeScript, "run", _capture)

    user = await _admin(client, db_session, "pipe-ctx@example.com")
    await _override(db_session, "render_font_size", 77)

    created = await client.post(
        "/api/projects", json={"title": "테스트", "topic": "주제", "auto_run": False}
    )
    project_id = created.json()["project"]["id"]

    conn = await raw_connection(db_session)
    project = pipeline.decode_stage(
        dict(await queries.find_project_by_id(conn, id=project_id))
    )
    stage = pipeline.decode_stage(
        dict(await queries.find_stage(conn, project_id=project_id, name="script"))
    )

    assert await pipeline.queue_stage(db_session, stage["id"], actor_id=user.id)
    claimed = await pipeline.claim_stage(db_session, stage["id"], actor_id=user.id)
    assert claimed is not None
    await pipeline.run_claimed_stage(db_session, project, claimed, actor_id=user.id)

    assert seen["render_font_size"] == 77
    # 프로젝트 자체 설정도 그대로 남는다 (병합에서 프로젝트 쪽이 이긴다)
    assert seen["auto_run"] is False
