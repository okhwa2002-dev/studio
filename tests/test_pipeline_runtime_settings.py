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
    # 프로젝트 자체 설정(런타임 설정에는 없는 키)도 그대로 살아남는다.
    # 주의: 이 두 단언은 서로 다른 키를 확인하므로 "프로젝트가 런타임을 이긴다"는
    # 병합 순서 자체는 증명하지 못한다 — 겹치는 키가 없으면 병합을 반대로
    # 뒤집어도({**project, **runtime}) 이 테스트는 그대로 통과한다. 병합 순서
    # 우선순위는 아래 test_project_settings_override_runtime_settings_on_conflict가
    # 겹치는 키로 증명한다.
    assert seen["auto_run"] is False


async def test_project_settings_override_runtime_settings_on_conflict(
    client, db_session, monkeypatch
):
    """겹치는 키에서는 프로젝트 설정이 런타임 설정을 이긴다 — 병합 순서 자체를 증명한다.

    render_font_size를 런타임 설정(77)과 프로젝트 설정(999) 양쪽에 서로 다른 값으로
    넣고, ctx.settings에 프로젝트 쪽 값(999)이 남는지 확인한다. 두 값을 서로 다른
    키에만 넣으면(예: 런타임에만 있는 키 vs 프로젝트에만 있는 키) 병합 순서를
    {**project, **runtime}으로 뒤집는 버그가 있어도 테스트가 통과해버린다 — 그래서
    반드시 같은 키를 양쪽에 다른 값으로 채워 충돌을 만든다.
    """
    from app.core import pipeline
    from app.providers.base import StageResult
    from app.providers.script.fake import FakeScript

    seen: dict = {}

    async def _capture(self, ctx):
        seen.update(ctx.settings)
        return StageResult(output={"scenes": []})

    monkeypatch.setattr(FakeScript, "run", _capture)

    user = await _admin(client, db_session, "pipe-conflict@example.com")
    await _override(db_session, "render_font_size", 77)  # 런타임 설정 쪽 값

    created = await client.post(
        "/api/projects", json={"title": "테스트", "topic": "주제", "auto_run": False}
    )
    project_id = created.json()["project"]["id"]

    # 프로젝트 자체 설정(projects.settings)에 같은 키를 다른 값으로 직접 넣는다.
    # 이 저장소에는 프로젝트 settings만 갱신하는 별도 쿼리가 없어 raw SQL로 직접 UPDATE한다.
    conn = await raw_connection(db_session)
    await conn.execute(
        "UPDATE projects SET settings = $1::jsonb WHERE id = $2",
        json.dumps({"auto_run": False, "render_font_size": 999}),
        project_id,
    )

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

    # 겹치는 키에서 프로젝트 쪽 값(999)이 런타임 쪽 값(77)을 이긴다.
    assert seen["render_font_size"] == 999
