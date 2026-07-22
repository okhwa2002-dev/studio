from app.auth.security import hash_password
from app.constants import UserRole, UserStatus
from app.models.user import User

_PW = "pw12345"


async def _login(client, db_session, email: str) -> User:
    # tests/test_api_projects.py의 _login과 동일한 흐름(가입 → 승인 상태로 커밋 → 로그인).
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


async def _project_with_voice_run(client, db_session) -> int:
    """프로젝트 생성 → script 실행·승인 → voice 실행(큐 드레인까지). (conftest가 provider를 fake로 강제)"""
    detail = (await client.post("/api/projects", json={"title": "t", "topic": "주제"})).json()
    pid = detail["project"]["id"]
    script_run = await client.post(f"/api/projects/{pid}/stages/script/run")
    script_id = next(s for s in script_run.json()["stages"] if s["name"] == "script")["id"]
    await _drain(db_session, script_id)
    await client.post(f"/api/projects/{pid}/stages/script/approve")
    voice_run = await client.post(f"/api/projects/{pid}/stages/voice/run")
    voice_id = next(s for s in voice_run.json()["stages"] if s["name"] == "voice")["id"]
    await _drain(db_session, voice_id)
    return pid


async def test_owner_downloads_audio(client, db_session, monkeypatch, tmp_path):
    from app.utils import storage

    monkeypatch.setattr(storage, "_root", lambda: tmp_path)
    await _login(client, db_session, "asset-owner@example.com")
    pid = await _project_with_voice_run(client, db_session)

    r = await client.get(f"/api/projects/{pid}/stages/voice/asset")
    assert r.status_code == 200
    assert r.headers["content-type"] == "audio/mpeg"
    assert len(r.content) > 0


async def test_other_user_gets_404(client, db_session, monkeypatch, tmp_path):
    from app.utils import storage

    monkeypatch.setattr(storage, "_root", lambda: tmp_path)
    await _login(client, db_session, "asset-a@example.com")
    pid = await _project_with_voice_run(client, db_session)

    # 다른 사용자로 로그인(쿠키 교체) → 남의 프로젝트 산출물은 존재 자체를 숨긴다
    await _login(client, db_session, "asset-b@example.com")
    r = await client.get(f"/api/projects/{pid}/stages/voice/asset")
    assert r.status_code == 404
    # 라우트 부재 등 무관한 404가 아니라 우리 격리 로직이 낸 404인지 고정한다
    assert r.json()["code"] == "RESOURCE_NOT_FOUND"


async def test_regenerate_replaces_asset_and_stays_downloadable(client, db_session, monkeypatch, tmp_path):
    from app.utils import storage

    monkeypatch.setattr(storage, "_root", lambda: tmp_path)
    await _login(client, db_session, "asset-regen@example.com")
    pid = await _project_with_voice_run(client, db_session)

    first = await client.get(f"/api/projects/{pid}/stages/voice/asset")
    assert first.status_code == 200
    first_bytes = first.content

    regen = await client.post(f"/api/projects/{pid}/stages/voice/regenerate")
    assert regen.status_code == 202
    stage_id = next(s for s in regen.json()["stages"] if s["name"] == "voice")["id"]
    await _drain(db_session, stage_id)

    second = await client.get(f"/api/projects/{pid}/stages/voice/asset")
    assert second.status_code == 200  # C1: 재생성 후에도 파일이 남아 있어야 한다
    assert second.content != first_bytes  # FakeVoice가 attempt를 바이트에 담으므로 내용이 달라야 한다


async def test_missing_asset_gets_404(client, db_session, monkeypatch, tmp_path):
    from app.utils import storage

    monkeypatch.setattr(storage, "_root", lambda: tmp_path)
    await _login(client, db_session, "asset-none@example.com")
    detail = (await client.post("/api/projects", json={"title": "t", "topic": "주제"})).json()
    pid = detail["project"]["id"]
    # script 단계는 파일 산출물이 없다
    r = await client.get(f"/api/projects/{pid}/stages/script/asset")
    assert r.status_code == 404
    assert r.json()["code"] == "RESOURCE_NOT_FOUND"
