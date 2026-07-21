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


async def _project_through_captions(client) -> int:
    detail = (await client.post("/api/projects", json={"title": "t", "topic": "주제"})).json()
    pid = detail["project"]["id"]
    for stage in ("script", "voice", "captions"):
        await client.post(f"/api/projects/{pid}/stages/{stage}/run")
        await client.post(f"/api/projects/{pid}/stages/{stage}/approve")
    return pid


async def test_running_render_produces_video(client, db_session, monkeypatch, tmp_path):
    from app.utils import storage

    monkeypatch.setattr(storage, "_root", lambda: tmp_path)
    await _login(client, db_session, "render-run@example.com")
    pid = await _project_through_captions(client)

    detail = (await client.post(f"/api/projects/{pid}/stages/render/run")).json()
    render = next(s for s in detail["stages"] if s["name"] == "render")
    assert render["status"] == "NEEDS_REVIEW"
    assert render["output"]["width"] == 1080

    asset = await client.get(f"/api/projects/{pid}/stages/render/asset")
    assert asset.status_code == 200
    assert asset.headers["content-type"] == "video/mp4"


async def test_approving_render_completes_the_project(client, db_session, monkeypatch, tmp_path):
    from app.utils import storage

    monkeypatch.setattr(storage, "_root", lambda: tmp_path)
    await _login(client, db_session, "render-done@example.com")
    pid = await _project_through_captions(client)

    await client.post(f"/api/projects/{pid}/stages/render/run")
    detail = (await client.post(f"/api/projects/{pid}/stages/render/approve")).json()
    assert detail["project"]["status"] == "DONE"


async def test_other_user_cannot_download_video(client, db_session, monkeypatch, tmp_path):
    from app.utils import storage

    monkeypatch.setattr(storage, "_root", lambda: tmp_path)
    await _login(client, db_session, "render-iso-a@example.com")
    pid = await _project_through_captions(client)
    await client.post(f"/api/projects/{pid}/stages/render/run")

    await _login(client, db_session, "render-iso-b@example.com")
    r = await client.get(f"/api/projects/{pid}/stages/render/asset")
    assert r.status_code == 404
    assert r.json()["code"] == "RESOURCE_NOT_FOUND"
