import asyncio
import json

from app.api.projects import project_events
from app.auth.security import hash_password
from app.constants import UserRole, UserStatus
from app.db import raw_connection
from app.models.user import User
from app.queries import queries


async def _login(client, db_session, email: str, role: str = UserRole.MEMBER) -> User:
    user = User(email=email, password_hash=hash_password("pw12345"),
                role=role, status=UserStatus.ACTIVE, name="홍길동")
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    resp = await client.post("/api/auth/login", json={"email": email, "password": "pw12345"})
    assert resp.status_code == 200
    return user


async def _as_current_user(db_session, user_id: int) -> dict:
    conn = await raw_connection(db_session)
    row = await queries.find_by_id(conn, id=user_id)
    user = dict(row)
    user.pop("password_hash", None)
    return user


async def test_list_all_projects_includes_owner(client, db_session):
    # 회원이 프로젝트를 만들고, 관리자가 전체 목록에서 소유자 정보와 함께 본다.
    await _login(client, db_session, "owner@example.com")
    pid = (await client.post(
        "/api/projects", json={"title": "바다 영상", "topic": "거북"}
    )).json()["project"]["id"]

    await _login(client, db_session, "admin@example.com", role=UserRole.ADMIN)
    resp = await client.get("/api/admin/projects")
    assert resp.status_code == 200
    row = next(p for p in resp.json() if p["id"] == pid)
    assert row["title"] == "바다 영상"
    assert row["owner_email"] == "owner@example.com"
    assert row["owner_name"] == "홍길동"


async def test_admin_projects_rejects_non_admin(client, db_session):
    await _login(client, db_session, "member@example.com")
    resp = await client.get("/api/admin/projects")
    assert resp.status_code == 403


async def test_admin_can_read_other_users_project_events(client, db_session):
    # 관리자는 남의 프로젝트 상세 스트림(읽기)을 열 수 있다 — 스냅샷이 나와야 한다.
    await _login(client, db_session, "owner2@example.com")
    pid = (await client.post(
        "/api/projects", json={"title": "t", "topic": "달"}
    )).json()["project"]["id"]

    admin = User(email="admin2@example.com", password_hash=hash_password("pw12345"),
                 role=UserRole.ADMIN, status=UserStatus.ACTIVE, name="관리자")
    db_session.add(admin)
    await db_session.commit()
    await db_session.refresh(admin)
    admin_payload = await _as_current_user(db_session, admin.id)

    resp = await project_events(pid, user=admin_payload, db=db_session)
    assert resp.status_code == 200
    chunk = await asyncio.wait_for(resp.body_iterator.__anext__(), timeout=5)
    snapshot = json.loads(chunk[len("data: "):])
    assert snapshot["type"] == "snapshot"
    assert snapshot["project"]["id"] == pid
    await resp.body_iterator.aclose()


async def test_admin_cannot_run_other_users_project(client, db_session):
    # 읽기는 열어도 쓰기(실행)는 소유자 전용이라 관리자가 호출하면 404다.
    await _login(client, db_session, "owner3@example.com")
    pid = (await client.post(
        "/api/projects", json={"title": "t", "topic": "산"}
    )).json()["project"]["id"]

    await _login(client, db_session, "admin3@example.com", role=UserRole.ADMIN)
    resp = await client.post(f"/api/projects/{pid}/stages/script/run")
    assert resp.status_code == 404
