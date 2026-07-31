"""프로젝트 소프트 삭제 — DELETE /api/projects/{id}"""

from app.auth.security import hash_password
from app.constants import StageStatus, UserRole, UserStatus
from app.db import raw_connection
from app.models.user import User
from app.queries import queries
from app.utils.time import now_local


async def _login(client, db_session, email: str, role: str = UserRole.MEMBER) -> User:
    user = User(
        email=email,
        password_hash=hash_password("pw12345"),
        role=role,
        status=UserStatus.ACTIVE,
    )
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    resp = await client.post("/api/auth/login", json={"email": email, "password": "pw12345"})
    assert resp.status_code == 200
    return user


async def _create_project(client, title: str = "지울 프로젝트") -> int:
    resp = await client.post("/api/projects", json={"title": title, "topic": "주제"})
    assert resp.status_code == 201
    return resp.json()["project"]["id"]


async def _set_stage_status(db_session, project_id: int, status: str) -> None:
    """단계 상태를 직접 바꾼다 — 진행 중 판정을 태우기 위한 준비다."""
    conn = await raw_connection(db_session)
    stage = await queries.find_stage(conn, project_id=project_id, name="script")
    await queries.update_stage_status(
        conn, id=stage["id"], status=status, updated_at=now_local(), updated_by=None
    )
    await db_session.commit()


async def _read_project_row(db_session, project_id: int):
    """삭제된 행까지 보려면 find_project_by_id를 쓸 수 없다(deleted_at IS NULL로 걸러진다)."""
    conn = await raw_connection(db_session)
    return await conn.fetchrow(
        "SELECT id, deleted_at, deleted_by FROM projects WHERE id = $1", project_id
    )


async def test_delete_returns_deleted_at(client, db_session):
    await _login(client, db_session, "del1@example.com")
    pid = await _create_project(client)

    resp = await client.delete(f"/api/projects/{pid}")
    assert resp.status_code == 200
    assert resp.json()["id"] == pid
    assert resp.json()["deleted_at"] is not None


async def test_delete_is_soft_and_records_actor(client, db_session):
    """행은 남고 deleted_at·deleted_by가 채워진다 — 하드 삭제가 아님을 고정한다."""
    user = await _login(client, db_session, "del2@example.com")
    pid = await _create_project(client)

    assert (await client.delete(f"/api/projects/{pid}")).status_code == 200

    row = await _read_project_row(db_session, pid)
    assert row is not None, "행이 지워지면 안 된다(소프트 삭제)"
    assert row["deleted_at"] is not None
    assert row["deleted_by"] == user.id


async def test_deleted_project_disappears_from_list(client, db_session):
    await _login(client, db_session, "del3@example.com")
    kept = await _create_project(client, "남는 프로젝트")
    removed = await _create_project(client, "지울 프로젝트")

    assert (await client.delete(f"/api/projects/{removed}")).status_code == 200

    ids = [p["id"] for p in (await client.get("/api/projects")).json()]
    assert removed not in ids
    assert kept in ids


async def test_deleted_project_detail_is_404(client, db_session):
    await _login(client, db_session, "del4@example.com")
    pid = await _create_project(client)

    assert (await client.delete(f"/api/projects/{pid}")).status_code == 200
    assert (await client.get(f"/api/projects/{pid}")).status_code == 404


async def test_deleted_project_events_is_404(client, db_session):
    """SSE는 스트림 밖에서 진짜 404로 답해야 한다."""
    await _login(client, db_session, "del5@example.com")
    pid = await _create_project(client)

    assert (await client.delete(f"/api/projects/{pid}")).status_code == 200
    assert (await client.get(f"/api/projects/{pid}/events")).status_code == 404


async def test_deleted_project_asset_is_404(client, db_session):
    await _login(client, db_session, "del6@example.com")
    pid = await _create_project(client)

    assert (await client.delete(f"/api/projects/{pid}")).status_code == 200
    resp = await client.get(f"/api/projects/{pid}/stages/voice/asset")
    assert resp.status_code == 404


async def test_deleted_project_disappears_from_admin_list(client, db_session):
    owner = await _login(client, db_session, "del7-owner@example.com")
    pid = await _create_project(client)
    assert (await client.delete(f"/api/projects/{pid}")).status_code == 200

    client.cookies.clear()
    await _login(client, db_session, "del7-admin@example.com", role=UserRole.ADMIN)

    ids = [p["id"] for p in (await client.get("/api/admin/projects")).json()]
    assert pid not in ids
    assert owner.id is not None


async def test_deleted_project_drops_out_of_dashboard(client, db_session):
    await _login(client, db_session, "del8@example.com")
    pid = await _create_project(client)

    before = (await client.get("/api/dashboard/summary")).json()["projects"]["total"]
    assert (await client.delete(f"/api/projects/{pid}")).status_code == 200
    after = (await client.get("/api/dashboard/summary")).json()["projects"]["total"]
    assert after == before - 1


async def test_deleted_project_drops_out_of_attention_list(client, db_session):
    """실패한 단계가 있어 '조치 필요'에 올라온 프로젝트도 삭제하면 빠진다."""
    await _login(client, db_session, "del9@example.com")
    pid = await _create_project(client)
    await _set_stage_status(db_session, pid, StageStatus.FAILED)

    attention = (await client.get("/api/dashboard/summary")).json()["attention"]
    assert pid in [p["id"] for p in attention], "준비 실패: 조치 필요 목록에 올라와야 한다"

    assert (await client.delete(f"/api/projects/{pid}")).status_code == 200

    attention = (await client.get("/api/dashboard/summary")).json()["attention"]
    assert pid not in [p["id"] for p in attention]


async def test_delete_rejects_running_stage(client, db_session):
    await _login(client, db_session, "del10@example.com")
    pid = await _create_project(client)
    await _set_stage_status(db_session, pid, StageStatus.RUNNING)

    resp = await client.delete(f"/api/projects/{pid}")
    assert resp.status_code == 409
    assert resp.json()["code"] == "PROJECT_BUSY"

    row = await _read_project_row(db_session, pid)
    assert row["deleted_at"] is None, "거절했으면 삭제 표시도 없어야 한다"


async def test_delete_rejects_queued_stage(client, db_session):
    await _login(client, db_session, "del11@example.com")
    pid = await _create_project(client)
    await _set_stage_status(db_session, pid, StageStatus.QUEUED)

    resp = await client.delete(f"/api/projects/{pid}")
    assert resp.status_code == 409
    assert resp.json()["code"] == "PROJECT_BUSY"


async def test_delete_allows_failed_stage(client, db_session):
    """워커가 손대지 않는 정지 상태는 막지 않는다."""
    await _login(client, db_session, "del12@example.com")
    pid = await _create_project(client)
    await _set_stage_status(db_session, pid, StageStatus.FAILED)

    assert (await client.delete(f"/api/projects/{pid}")).status_code == 200


async def test_delete_allows_needs_review_stage(client, db_session):
    await _login(client, db_session, "del13@example.com")
    pid = await _create_project(client)
    await _set_stage_status(db_session, pid, StageStatus.NEEDS_REVIEW)

    assert (await client.delete(f"/api/projects/{pid}")).status_code == 200


async def test_cannot_delete_other_users_project(client, db_session):
    await _login(client, db_session, "del14-owner@example.com")
    pid = await _create_project(client)

    client.cookies.clear()
    await _login(client, db_session, "del14-other@example.com")

    assert (await client.delete(f"/api/projects/{pid}")).status_code == 404

    row = await _read_project_row(db_session, pid)
    assert row["deleted_at"] is None, "남의 프로젝트는 그대로여야 한다"


async def test_admin_cannot_delete_others_project(client, db_session):
    """관리자는 열람만 한다 — 삭제는 소유자 전용이다."""
    await _login(client, db_session, "del15-owner@example.com")
    pid = await _create_project(client)

    client.cookies.clear()
    await _login(client, db_session, "del15-admin@example.com", role=UserRole.ADMIN)

    assert (await client.delete(f"/api/projects/{pid}")).status_code == 404

    row = await _read_project_row(db_session, pid)
    assert row["deleted_at"] is None


async def test_deleting_twice_returns_404(client, db_session):
    await _login(client, db_session, "del16@example.com")
    pid = await _create_project(client)

    assert (await client.delete(f"/api/projects/{pid}")).status_code == 200
    assert (await client.delete(f"/api/projects/{pid}")).status_code == 404


async def test_delete_unknown_project_returns_404(client, db_session):
    await _login(client, db_session, "del17@example.com")

    assert (await client.delete("/api/projects/999999")).status_code == 404


async def test_delete_requires_auth(client):
    assert (await client.delete("/api/projects/1")).status_code == 401


async def _project_with_running_stage(client, db_session) -> int:
    """RUNNING 단계가 있는 프로젝트를 만든다 — 삭제가 409(PROJECT_BUSY)로 거절되는 준비 상태다."""
    pid = await _create_project(client)
    await _set_stage_status(db_session, pid, StageStatus.RUNNING)
    return pid


async def test_delete_is_recorded_with_title(client, db_session):
    await _login(client, db_session, "delete-audit@example.com")
    created = await client.post(
        "/api/projects", json={"title": "여행 브이로그", "topic": "제주도"}
    )
    project_id = created.json()["project"]["id"]

    resp = await client.delete(f"/api/projects/{project_id}")
    assert resp.status_code == 200

    conn = await raw_connection(db_session)
    rows = await conn.fetch("SELECT * FROM audit_logs WHERE action = 'PROJECT_DELETE'")
    assert len(rows) == 1
    assert rows[0]["target_type"] == "PROJECT"
    assert rows[0]["target_id"] == project_id
    assert rows[0]["target_label"] == "여행 브이로그"
    assert rows[0]["http_method"] == "DELETE"


async def test_rejected_delete_is_not_recorded(client, db_session):
    """409로 거절된 삭제는 아무 일도 하지 않았다 — 기록도 남지 않는다.

    여기서는 rollback()을 쓰지 않는다: "커밋됐는가"가 아니라 "기록이 아예 없는가"를
    보기 때문이다. rollback을 넣으면 회귀로 생긴 커밋 전 INSERT까지 지워버려 테스트가
    항상 통과하게 된다.
    """
    await _login(client, db_session, "busy-audit@example.com")
    project_id = await _project_with_running_stage(client, db_session)

    resp = await client.delete(f"/api/projects/{project_id}")
    assert resp.status_code == 409

    conn = await raw_connection(db_session)
    count = await conn.fetchval("SELECT COUNT(*) FROM audit_logs WHERE action = 'PROJECT_DELETE'")
    assert count == 0
