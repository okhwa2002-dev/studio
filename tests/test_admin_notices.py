from datetime import timedelta

from app.auth.security import hash_password
from app.constants import NoticeStatus, UserRole, UserStatus, YN
from app.db import raw_connection
from app.models.user import User
from app.utils.time import now_local


async def _login(client, db_session, email: str, role: str = UserRole.ADMIN) -> User:
    user = User(
        email=email,
        password_hash=hash_password("pw12345"),
        role=role,
        status=UserStatus.ACTIVE,
        name="관리자",
    )
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)

    resp = await client.post("/api/auth/login", json={"email": email, "password": "pw12345"})
    assert resp.status_code == 200
    return user


def _payload(**overrides) -> dict:
    payload = {
        "title": "서버 점검 안내",
        "body": "7/30 02:00~04:00 점검이 있습니다.",
        "status": NoticeStatus.DRAFT,
        "pinned_yn": YN.N,
        "popup_yn": YN.N,
        "starts_at": None,
        "ends_at": None,
    }
    payload.update(overrides)
    return payload


async def test_create_draft_returns_201_with_id(client, db_session):
    await _login(client, db_session, "admin-create@example.com")

    resp = await client.post("/api/admin/notices", json=_payload())
    assert resp.status_code == 201
    assert isinstance(resp.json()["id"], int)


async def test_publishing_without_starts_at_fills_it(client, db_session):
    """게시로 올릴 때 시작 일시를 지정하지 않으면 그 순간이 게시일이 된다."""
    await _login(client, db_session, "admin-publish@example.com")
    before = now_local()

    resp = await client.post(
        "/api/admin/notices", json=_payload(status=NoticeStatus.PUBLISHED)
    )
    assert resp.status_code == 201

    listed = await client.get("/api/admin/notices")
    row = next(r for r in listed.json() if r["id"] == resp.json()["id"])
    assert row["starts_at"] is not None
    assert row["starts_at"][:10] == before.isoformat()[:10]


async def test_draft_keeps_starts_at_null_even_if_given(client, db_session):
    """임시저장은 '아직 게시된 적 없음'이므로 게시일을 갖지 않는다."""
    await _login(client, db_session, "admin-draft@example.com")

    resp = await client.post(
        "/api/admin/notices",
        json=_payload(status=NoticeStatus.DRAFT, starts_at=now_local().isoformat()),
    )
    assert resp.status_code == 201

    listed = await client.get("/api/admin/notices")
    row = next(r for r in listed.json() if r["id"] == resp.json()["id"])
    assert row["starts_at"] is None


async def test_ends_at_before_starts_at_returns_400(client, db_session):
    await _login(client, db_session, "admin-period@example.com")
    starts = now_local()

    resp = await client.post(
        "/api/admin/notices",
        json=_payload(
            status=NoticeStatus.PUBLISHED,
            starts_at=starts.isoformat(),
            ends_at=(starts - timedelta(hours=1)).isoformat(),
        ),
    )
    assert resp.status_code == 400


async def test_blank_title_returns_422(client, db_session):
    await _login(client, db_session, "admin-blank@example.com")

    resp = await client.post("/api/admin/notices", json=_payload(title="   "))
    assert resp.status_code == 422


async def test_invalid_yn_returns_422(client, db_session):
    await _login(client, db_session, "admin-yn@example.com")

    resp = await client.post("/api/admin/notices", json=_payload(pinned_yn="TRUE"))
    assert resp.status_code == 422


async def test_list_includes_author_name(client, db_session):
    await _login(client, db_session, "admin-author@example.com")

    created = await client.post("/api/admin/notices", json=_payload(title="작성자 확인"))
    listed = await client.get("/api/admin/notices")
    assert listed.status_code == 200
    row = next(r for r in listed.json() if r["id"] == created.json()["id"])
    assert row["created_by_name"] == "관리자"


async def test_member_cannot_access_admin_notices(client, db_session):
    await _login(client, db_session, "member-notices@example.com", role=UserRole.MEMBER)

    assert (await client.get("/api/admin/notices")).status_code == 403
    assert (await client.post("/api/admin/notices", json=_payload())).status_code == 403


async def test_update_changes_fields(client, db_session):
    await _login(client, db_session, "admin-update@example.com")
    created = await client.post("/api/admin/notices", json=_payload())
    notice_id = created.json()["id"]

    resp = await client.patch(
        f"/api/admin/notices/{notice_id}",
        json=_payload(title="수정된 제목", pinned_yn=YN.Y, status=NoticeStatus.PUBLISHED),
    )
    assert resp.status_code == 200

    listed = await client.get("/api/admin/notices")
    row = next(r for r in listed.json() if r["id"] == notice_id)
    assert row["title"] == "수정된 제목"
    assert row["pinned_yn"] == YN.Y
    assert row["status"] == NoticeStatus.PUBLISHED


async def test_reverting_to_draft_clears_starts_at(client, db_session):
    """게시했던 공지를 임시저장으로 되돌리면 게시일이 비워진다."""
    await _login(client, db_session, "admin-revert@example.com")
    created = await client.post(
        "/api/admin/notices", json=_payload(status=NoticeStatus.PUBLISHED)
    )
    notice_id = created.json()["id"]
    # 되돌리기 전 전제조건: 게시되었으므로 게시일이 채워져 있어야 한다. 이 assert가
    # 없으면 게시가 starts_at을 채우는 동작이 깨져도 이 테스트는 계속 통과한다.
    published = await client.get("/api/admin/notices")
    assert next(r for r in published.json() if r["id"] == notice_id)["starts_at"] is not None

    resp = await client.patch(
        f"/api/admin/notices/{notice_id}", json=_payload(status=NoticeStatus.DRAFT)
    )
    assert resp.status_code == 200

    listed = await client.get("/api/admin/notices")
    row = next(r for r in listed.json() if r["id"] == notice_id)
    assert row["starts_at"] is None


async def test_update_unknown_notice_returns_404(client, db_session):
    await _login(client, db_session, "admin-update-404@example.com")

    resp = await client.patch("/api/admin/notices/999999", json=_payload())
    assert resp.status_code == 404


async def test_delete_keeps_row_but_hides_from_list(client, db_session):
    """소프트 삭제는 행을 지우지 않고 목록에서만 뺀다."""
    await _login(client, db_session, "admin-delete@example.com")
    created = await client.post("/api/admin/notices", json=_payload(title="지울 공지"))
    notice_id = created.json()["id"]

    resp = await client.delete(f"/api/admin/notices/{notice_id}")
    assert resp.status_code == 200
    assert resp.json()["deleted_at"] is not None

    listed = await client.get("/api/admin/notices")
    assert all(r["id"] != notice_id for r in listed.json())

    from sqlalchemy import select

    from app.models.notice import Notice

    result = await db_session.execute(select(Notice).where(Notice.id == notice_id))
    row = result.scalar_one()
    assert row.deleted_at is not None
    assert row.deleted_by is not None


async def test_delete_twice_returns_404(client, db_session):
    await _login(client, db_session, "admin-delete-twice@example.com")
    created = await client.post("/api/admin/notices", json=_payload())
    notice_id = created.json()["id"]

    assert (await client.delete(f"/api/admin/notices/{notice_id}")).status_code == 200
    assert (await client.delete(f"/api/admin/notices/{notice_id}")).status_code == 404


async def test_member_cannot_update_or_delete(client, db_session):
    await _login(client, db_session, "member-write@example.com", role=UserRole.MEMBER)

    assert (await client.patch("/api/admin/notices/1", json=_payload())).status_code == 403
    assert (await client.delete("/api/admin/notices/1")).status_code == 403


async def test_notice_lifecycle_is_recorded(client, db_session):
    await _login(client, db_session, "notice-audit@example.com")

    created = await client.post("/api/admin/notices", json=_payload(title="점검 공지"))
    notice_id = created.json()["id"]
    await client.patch(
        f"/api/admin/notices/{notice_id}", json=_payload(title="점검 공지(수정)")
    )
    await client.delete(f"/api/admin/notices/{notice_id}")

    conn = await raw_connection(db_session)
    rows = await conn.fetch(
        "SELECT * FROM audit_logs WHERE target_type = 'NOTICE' ORDER BY id"
    )
    assert [r["action"] for r in rows] == ["NOTICE_CREATE", "NOTICE_UPDATE", "NOTICE_DELETE"]
    assert rows[0]["target_id"] == notice_id
    assert rows[0]["target_label"] == "점검 공지"
    # 수정 기록의 라벨은 **변경 전** 제목이다 — 관리자가 기억하는 옛 제목으로 검색해서
    # "누가 바꿨는지"를 찾을 수 있어야 한다. 변경 후 제목은 summary에 남아 함께 검색된다.
    assert rows[1]["target_label"] == "점검 공지"
    assert "점검 공지(수정)" in rows[1]["summary"]
    assert rows[2]["target_label"] == "점검 공지(수정)"
