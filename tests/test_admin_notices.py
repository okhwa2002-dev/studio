from datetime import timedelta

from app.auth.security import hash_password
from app.constants import NoticeStatus, UserRole, UserStatus, YN
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
