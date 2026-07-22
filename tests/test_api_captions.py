from app.auth.security import hash_password
from app.constants import UserRole, UserStatus
from app.models.user import User

_PW = "pw12345"


async def _login(client, db_session, email: str) -> User:
    user = User(email=email, password_hash=hash_password(_PW),
                role=UserRole.MEMBER, status=UserStatus.ACTIVE)
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    resp = await client.post("/api/auth/login", json={"email": email, "password": _PW})
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


async def _run_and_approve(client, db_session, pid: int, name: str) -> None:
    """run(202+QUEUED) → 워커로 완료(drain) → approve(200)까지 한 단계를 끝낸다."""
    run = await client.post(f"/api/projects/{pid}/stages/{name}/run")
    assert run.status_code == 202
    stage_id = next(s for s in run.json()["stages"] if s["name"] == name)["id"]
    await _drain(db_session, stage_id)
    approved = await client.post(f"/api/projects/{pid}/stages/{name}/approve")
    assert approved.status_code == 200


async def _project_through_voice(client, db_session) -> int:
    """프로젝트 생성 → script 실행·승인 → voice 실행·승인. (conftest가 provider를 fake로 강제)"""
    detail = (await client.post("/api/projects", json={"title": "t", "topic": "주제"})).json()
    pid = detail["project"]["id"]
    await _run_and_approve(client, db_session, pid, "script")
    await _run_and_approve(client, db_session, pid, "voice")
    return pid


async def test_running_captions_produces_words_and_srt(client, db_session, monkeypatch, tmp_path):
    from app.utils import storage

    monkeypatch.setattr(storage, "_root", lambda: tmp_path)
    await _login(client, db_session, "cap-run@example.com")
    pid = await _project_through_voice(client, db_session)

    run = await client.post(f"/api/projects/{pid}/stages/captions/run")
    assert run.status_code == 202
    stage_id = next(s for s in run.json()["stages"] if s["name"] == "captions")["id"]
    await _drain(db_session, stage_id)

    detail = (await client.get(f"/api/projects/{pid}")).json()
    captions = next(s for s in detail["stages"] if s["name"] == "captions")
    assert captions["status"] == "NEEDS_REVIEW"
    assert captions["output"]["word_count"] > 0
    assert captions["output"]["words"][0]["w"]  # 프론트가 srt를 파싱하지 않게 하는 계약

    asset = await client.get(f"/api/projects/{pid}/stages/captions/asset")
    assert asset.status_code == 200
    assert asset.headers["content-type"] == "application/x-subrip"
    assert "-->" in asset.content.decode("utf-8")


async def test_approving_captions_advances_to_render(client, db_session, monkeypatch, tmp_path):
    from app.utils import storage

    monkeypatch.setattr(storage, "_root", lambda: tmp_path)
    await _login(client, db_session, "cap-done@example.com")
    pid = await _project_through_voice(client, db_session)

    run = await client.post(f"/api/projects/{pid}/stages/captions/run")
    stage_id = next(s for s in run.json()["stages"] if s["name"] == "captions")["id"]
    await _drain(db_session, stage_id)
    detail = (await client.post(f"/api/projects/{pid}/stages/captions/approve")).json()
    assert detail["project"]["status"] == "REVIEW"
    assert detail["project"]["current_stage"] == "render"
    assert any(s["name"] == "render" and s["status"] == "PENDING" for s in detail["stages"])


async def test_other_user_cannot_download_srt(client, db_session, monkeypatch, tmp_path):
    from app.utils import storage

    monkeypatch.setattr(storage, "_root", lambda: tmp_path)
    await _login(client, db_session, "cap-a@example.com")
    pid = await _project_through_voice(client, db_session)
    run = await client.post(f"/api/projects/{pid}/stages/captions/run")
    assert run.status_code == 202
    stage_id = next(s for s in run.json()["stages"] if s["name"] == "captions")["id"]
    await _drain(db_session, stage_id)  # asset이 실제로 존재해야 404가 "격리" 때문임을 증명할 수 있다

    # 대비: 소유자는 200을 받는다 — 이게 없으면 _load_owned_project를 통째로 지워도
    # find_asset_by_stage → None → RESOURCE_NOT_FOUND로 똑같이 404가 나서 이 테스트가 vacuous해진다.
    owner_ok = await client.get(f"/api/projects/{pid}/stages/captions/asset")
    assert owner_ok.status_code == 200

    await _login(client, db_session, "cap-b@example.com")
    r = await client.get(f"/api/projects/{pid}/stages/captions/asset")
    assert r.status_code == 404
    assert r.json()["code"] == "RESOURCE_NOT_FOUND"


async def test_regenerate_replaces_srt(client, db_session, monkeypatch, tmp_path):
    from app.utils import storage

    monkeypatch.setattr(storage, "_root", lambda: tmp_path)
    await _login(client, db_session, "cap-regen@example.com")
    pid = await _project_through_voice(client, db_session)
    run = await client.post(f"/api/projects/{pid}/stages/captions/run")
    stage_id = next(s for s in run.json()["stages"] if s["name"] == "captions")["id"]
    await _drain(db_session, stage_id)

    from app.db import raw_connection
    from app.queries import queries

    conn = await raw_connection(db_session)
    stage = await queries.find_stage(conn, project_id=pid, name="captions")
    before = [dict(r) async for r in queries.list_assets_by_stage(conn, stage_id=stage["id"])]

    regen = await client.post(f"/api/projects/{pid}/stages/captions/regenerate")
    assert regen.status_code == 202
    await _drain(db_session, stage["id"])

    after = [dict(r) async for r in queries.list_assets_by_stage(conn, stage_id=stage["id"])]
    assert len(after) == 1  # 누적되지 않고 교체
    assert after[0]["id"] != before[0]["id"]
    assert (await client.get(f"/api/projects/{pid}/stages/captions/asset")).status_code == 200
