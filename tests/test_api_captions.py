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


async def _project_through_voice(client) -> int:
    """프로젝트 생성 → script 실행·승인 → voice 실행·승인. (conftest가 provider를 fake로 강제)"""
    detail = (await client.post("/api/projects", json={"title": "t", "topic": "주제"})).json()
    pid = detail["project"]["id"]
    await client.post(f"/api/projects/{pid}/stages/script/run")
    await client.post(f"/api/projects/{pid}/stages/script/approve")
    await client.post(f"/api/projects/{pid}/stages/voice/run")
    await client.post(f"/api/projects/{pid}/stages/voice/approve")
    return pid


async def test_running_captions_produces_words_and_srt(client, db_session, monkeypatch, tmp_path):
    from app.utils import storage

    monkeypatch.setattr(storage, "_root", lambda: tmp_path)
    await _login(client, db_session, "cap-run@example.com")
    pid = await _project_through_voice(client)

    detail = (await client.post(f"/api/projects/{pid}/stages/captions/run")).json()
    captions = next(s for s in detail["stages"] if s["name"] == "captions")
    assert captions["status"] == "NEEDS_REVIEW"
    assert captions["output"]["word_count"] > 0
    assert captions["output"]["words"][0]["w"]  # 프론트가 srt를 파싱하지 않게 하는 계약

    asset = await client.get(f"/api/projects/{pid}/stages/captions/asset")
    assert asset.status_code == 200
    assert asset.headers["content-type"] == "application/x-subrip"
    assert "-->" in asset.content.decode("utf-8")


async def test_approving_captions_completes_the_project(client, db_session, monkeypatch, tmp_path):
    from app.utils import storage

    monkeypatch.setattr(storage, "_root", lambda: tmp_path)
    await _login(client, db_session, "cap-done@example.com")
    pid = await _project_through_voice(client)

    await client.post(f"/api/projects/{pid}/stages/captions/run")
    detail = (await client.post(f"/api/projects/{pid}/stages/captions/approve")).json()
    assert detail["project"]["status"] == "DONE"


async def test_other_user_cannot_download_srt(client, db_session, monkeypatch, tmp_path):
    from app.utils import storage

    monkeypatch.setattr(storage, "_root", lambda: tmp_path)
    await _login(client, db_session, "cap-a@example.com")
    pid = await _project_through_voice(client)
    await client.post(f"/api/projects/{pid}/stages/captions/run")

    await _login(client, db_session, "cap-b@example.com")
    r = await client.get(f"/api/projects/{pid}/stages/captions/asset")
    assert r.status_code == 404
    assert r.json()["code"] == "RESOURCE_NOT_FOUND"


async def test_regenerate_replaces_srt(client, db_session, monkeypatch, tmp_path):
    from app.utils import storage

    monkeypatch.setattr(storage, "_root", lambda: tmp_path)
    await _login(client, db_session, "cap-regen@example.com")
    pid = await _project_through_voice(client)
    await client.post(f"/api/projects/{pid}/stages/captions/run")

    from app.db import raw_connection
    from app.queries import queries

    conn = await raw_connection(db_session)
    stage = await queries.find_stage(conn, project_id=pid, name="captions")
    before = [dict(r) async for r in queries.list_assets_by_stage(conn, stage_id=stage["id"])]

    assert (await client.post(f"/api/projects/{pid}/stages/captions/regenerate")).status_code == 200

    after = [dict(r) async for r in queries.list_assets_by_stage(conn, stage_id=stage["id"])]
    assert len(after) == 1  # 누적되지 않고 교체
    assert after[0]["id"] != before[0]["id"]
    assert (await client.get(f"/api/projects/{pid}/stages/captions/asset")).status_code == 200
