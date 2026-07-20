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


async def test_run_then_approve_flow(client, db_session):
    await _login(client, db_session, "b@example.com")
    pid = (await client.post("/api/projects", json={"title": "t", "topic": "우주"})).json()["project"]["id"]

    ran = await client.post(f"/api/projects/{pid}/stages/script/run")
    assert ran.status_code == 200
    stage = ran.json()["stages"][0]
    assert stage["status"] == StageStatus.NEEDS_REVIEW
    assert stage["output"]["title"].startswith("우주")

    approved = await client.post(f"/api/projects/{pid}/stages/script/approve")
    assert approved.status_code == 200
    body = approved.json()
    assert body["stages"][0]["status"] == StageStatus.APPROVED
    # script는 마지막 단계가 아니므로 승인 시 project는 DONE이 아니라 REVIEW로 전이하고,
    # voice 단계가 PENDING으로 새로 등록된다(다단계 전이 — 실행은 별도의 [실행] 호출로 시작).
    assert body["project"]["status"] == ProjectStatus.REVIEW
    assert body["project"]["current_stage"] == "voice"
    assert len(body["stages"]) == 2
    assert body["stages"][1]["name"] == "voice"
    assert body["stages"][1]["status"] == StageStatus.PENDING


async def test_regenerate_increments_attempt(client, db_session):
    await _login(client, db_session, "c@example.com")
    pid = (await client.post("/api/projects", json={"title": "t", "topic": "커피"})).json()["project"]["id"]
    await client.post(f"/api/projects/{pid}/stages/script/run")
    regen = await client.post(f"/api/projects/{pid}/stages/script/regenerate")
    assert regen.status_code == 200
    assert regen.json()["stages"][0]["attempt"] == 1
    assert regen.json()["stages"][0]["status"] == StageStatus.NEEDS_REVIEW


async def test_run_twice_conflicts(client, db_session):
    await _login(client, db_session, "d@example.com")
    pid = (await client.post("/api/projects", json={"title": "t", "topic": "산"})).json()["project"]["id"]
    await client.post(f"/api/projects/{pid}/stages/script/run")  # → NEEDS_REVIEW
    again = await client.post(f"/api/projects/{pid}/stages/script/run")
    assert again.status_code == 409


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
