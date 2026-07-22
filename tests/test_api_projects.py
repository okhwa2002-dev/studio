from app.auth.security import hash_password
from app.constants import ProjectStatus, StageStatus, UserRole, UserStatus
from app.models.user import User


async def _login(client, db_session, email: str) -> User:
    user = User(email=email, password_hash=hash_password("pw12345"),
                role=UserRole.MEMBER, status=UserStatus.ACTIVE)
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    resp = await client.post("/api/auth/login", json={"email": email, "password": "pw12345"})
    assert resp.status_code == 200
    return user


async def _drain(db_session, stage_id: int):
    """API는 큐에 넣기만 한다. 테스트에서는 워커를 직접 한 번 돌려 완료시킨다."""
    from contextlib import asynccontextmanager

    from app.core.worker import StageWorker

    @asynccontextmanager
    async def _factory():
        yield db_session

    await StageWorker(session_factory=_factory).run_one(stage_id)


async def test_requires_auth(client):
    resp = await client.get("/api/projects")
    assert resp.status_code == 401


async def test_create_project_seeds_pending_script_stage(client, db_session):
    await _login(client, db_session, "a@example.com")
    resp = await client.post("/api/projects", json={"title": "첫 프로젝트", "topic": "바다 거북"})
    assert resp.status_code == 201
    body = resp.json()
    assert body["project"]["status"] == ProjectStatus.DRAFT
    assert len(body["stages"]) == 1
    assert body["stages"][0]["name"] == "script"
    assert body["stages"][0]["status"] == StageStatus.PENDING


async def test_run_returns_202_and_queues(client, db_session):
    # 실행은 이제 요청 안에서 끝나지 않는다 — 즉시 202 + QUEUED로 돌아온다.
    from app.core.worker import get_worker

    await _login(client, db_session, "b@example.com")
    pid = (await client.post("/api/projects", json={"title": "t", "topic": "우주"})).json()["project"]["id"]

    ran = await client.post(f"/api/projects/{pid}/stages/script/run")
    assert ran.status_code == 202
    assert ran.json()["stages"][0]["status"] == StageStatus.QUEUED
    # 배선 고정: run이 전역 워커 큐에 실제로 넣지 않으면(리팩터/머지 충돌로 enqueue
    # 한 줄이 사라지면) 위 단언들은 여전히 초록이다 — 큐를 직접 들여다봐야 잡힌다.
    stage_id = ran.json()["stages"][0]["id"]
    assert get_worker()._queue.get_nowait() == stage_id


async def test_run_twice_conflicts(client, db_session):
    await _login(client, db_session, "d@example.com")
    pid = (await client.post("/api/projects", json={"title": "t", "topic": "산"})).json()["project"]["id"]
    assert (await client.post(f"/api/projects/{pid}/stages/script/run")).status_code == 202
    again = await client.post(f"/api/projects/{pid}/stages/script/run")
    assert again.status_code == 409


async def test_regenerate_returns_202_and_increments_attempt(client, db_session):
    from app.core.worker import StageWorker

    await _login(client, db_session, "c@example.com")
    pid = (await client.post("/api/projects", json={"title": "t", "topic": "커피"})).json()["project"]["id"]

    # 첫 실행을 워커로 완료시켜 NEEDS_REVIEW로 만든다.
    await client.post(f"/api/projects/{pid}/stages/script/run")
    stage_id = (await client.get(f"/api/projects/{pid}")).json()["stages"][0]["id"]
    await _drain(db_session, stage_id)

    from app.core.worker import get_worker

    regen = await client.post(f"/api/projects/{pid}/stages/script/regenerate")
    assert regen.status_code == 202
    body = regen.json()
    assert body["stages"][0]["attempt"] == 1
    assert body["stages"][0]["status"] == StageStatus.QUEUED
    # 배선 고정: regenerate도 전역 워커 큐에 실제로 넣어야 한다(I-3).
    assert get_worker()._queue.get_nowait() == body["stages"][0]["id"]


async def test_approve_still_returns_200(client, db_session):
    await _login(client, db_session, "approve@example.com")
    pid = (await client.post("/api/projects", json={"title": "t", "topic": "바다"})).json()["project"]["id"]
    await client.post(f"/api/projects/{pid}/stages/script/run")
    stage_id = (await client.get(f"/api/projects/{pid}")).json()["stages"][0]["id"]
    await _drain(db_session, stage_id)

    approved = await client.post(f"/api/projects/{pid}/stages/script/approve")
    assert approved.status_code == 200
    body = approved.json()
    assert body["stages"][0]["status"] == StageStatus.APPROVED
    assert body["project"]["current_stage"] == "voice"
    assert body["stages"][1]["status"] == StageStatus.PENDING


async def test_create_with_auto_run_queues_script(client, db_session):
    from app.core.worker import get_worker

    await _login(client, db_session, "autoapi@example.com")
    resp = await client.post(
        "/api/projects", json={"title": "t", "topic": "고래", "auto_run": True}
    )
    assert resp.status_code == 201
    body = resp.json()
    assert body["stages"][0]["status"] == StageStatus.QUEUED
    # 배선 고정: create(auto_run=True)도 전역 워커 큐에 실제로 넣어야 한다(I-3).
    assert get_worker()._queue.get_nowait() == body["stages"][0]["id"]


async def test_owner_isolation(client, db_session):
    owner = await _login(client, db_session, "owner@example.com")
    pid = (await client.post("/api/projects", json={"title": "t", "topic": "비밀"})).json()["project"]["id"]

    # 다른 사용자로 로그인(쿠키 교체) 후 접근 → 404
    await _login(client, db_session, "intruder@example.com")
    resp = await client.get(f"/api/projects/{pid}")
    assert resp.status_code == 404
    run = await client.post(f"/api/projects/{pid}/stages/script/run")
    assert run.status_code == 404


async def test_create_rejects_blank_title(client, db_session):
    await _login(client, db_session, "blank-title@example.com")
    resp = await client.post("/api/projects", json={"title": "   ", "topic": "주제"})
    assert resp.status_code == 422


async def test_create_rejects_blank_topic(client, db_session):
    await _login(client, db_session, "blank-topic@example.com")
    resp = await client.post("/api/projects", json={"title": "제목", "topic": ""})
    assert resp.status_code == 422


async def test_create_trims_surrounding_whitespace(client, db_session):
    await _login(client, db_session, "trim@example.com")
    resp = await client.post("/api/projects", json={"title": "  제목  ", "topic": "  주제 "})
    assert resp.status_code == 201
    assert resp.json()["project"]["title"] == "제목"
    assert resp.json()["project"]["topic"] == "주제"


async def test_create_uses_configured_provider(client, db_session):
    # conftest가 SCRIPT_PROVIDER=fake로 강제 → 생성된 script 단계 provider가 fake (가드)
    await _login(client, db_session, "provider-cfg@example.com")
    body = (await client.post("/api/projects", json={"title": "t", "topic": "주제"})).json()
    assert body["stages"][0]["provider"] == "fake"


async def test_create_uses_openai_when_configured(client, db_session, monkeypatch):
    # 설정이 openai면 생성된 단계 provider도 openai (create는 실행을 안 하므로 network 없음)
    monkeypatch.setattr(
        "app.api.projects.get_settings",
        lambda: __import__("types").SimpleNamespace(script_provider="openai"),
    )
    await _login(client, db_session, "provider-openai@example.com")
    body = (await client.post("/api/projects", json={"title": "t", "topic": "주제"})).json()
    assert body["stages"][0]["provider"] == "openai"
