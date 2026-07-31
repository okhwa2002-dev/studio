from datetime import timedelta

from sqlalchemy import func, select

from app.auth.security import hash_password
from app.constants import NoticeStatus, UserStatus, YN
from app.db import raw_connection
from app.models.notice import Notice
from app.models.notice_read import NoticeRead
from app.models.user import User
from app.utils.time import now_local


async def _login_member(client, db_session, email: str) -> User:
    user = User(
        email=email,
        password_hash=hash_password("pw12345"),
        status=UserStatus.ACTIVE,
        name="사용자",
    )
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)

    resp = await client.post("/api/auth/login", json={"email": email, "password": "pw12345"})
    assert resp.status_code == 200
    return user


async def _add_notice(db_session, **overrides) -> Notice:
    fields = {
        "title": "제목",
        "body": "본문",
        "status": NoticeStatus.PUBLISHED,
        "pinned_yn": YN.N,
        "popup_yn": YN.N,
        "starts_at": now_local() - timedelta(days=1),
        "ends_at": None,
    }
    fields.update(overrides)
    notice = Notice(**fields)
    db_session.add(notice)
    await db_session.commit()
    await db_session.refresh(notice)
    return notice


async def test_list_requires_login(client, db_session):
    resp = await client.get("/api/notices")
    assert resp.status_code == 401


async def test_list_returns_only_visible_notices(client, db_session):
    """임시저장·예약·종료·삭제된 공지는 사용자 목록에 나오지 않는다."""
    await _login_member(client, db_session, "member-list@example.com")
    now = now_local()

    visible = await _add_notice(db_session, title="게시중")
    await _add_notice(db_session, title="임시저장", status=NoticeStatus.DRAFT, starts_at=None)
    await _add_notice(db_session, title="예약", starts_at=now + timedelta(days=1))
    await _add_notice(
        db_session,
        title="종료",
        starts_at=now - timedelta(days=3),
        ends_at=now - timedelta(days=1),
    )
    await _add_notice(db_session, title="삭제됨", deleted_at=now)

    resp = await client.get("/api/notices")
    assert resp.status_code == 200
    titles = [row["title"] for row in resp.json()]
    assert titles == ["게시중"]
    assert resp.json()[0]["id"] == visible.id


async def test_list_puts_pinned_first_then_newest(client, db_session):
    await _login_member(client, db_session, "member-order@example.com")
    now = now_local()

    await _add_notice(db_session, title="오래된", starts_at=now - timedelta(days=5))
    await _add_notice(db_session, title="최신", starts_at=now - timedelta(days=1))
    await _add_notice(
        db_session, title="고정", pinned_yn=YN.Y, starts_at=now - timedelta(days=10)
    )

    resp = await client.get("/api/notices")
    assert [row["title"] for row in resp.json()] == ["고정", "최신", "오래된"]


async def test_list_marks_unread_by_default(client, db_session):
    await _login_member(client, db_session, "member-unread@example.com")
    await _add_notice(db_session)

    resp = await client.get("/api/notices")
    assert resp.json()[0]["is_read"] is False


async def test_mark_read_flips_is_read(client, db_session):
    await _login_member(client, db_session, "member-read@example.com")
    notice = await _add_notice(db_session)

    resp = await client.post(f"/api/notices/{notice.id}/read")
    assert resp.status_code == 200

    listed = await client.get("/api/notices")
    assert listed.json()[0]["is_read"] is True


async def test_mark_read_twice_keeps_single_row(client, db_session):
    """UNIQUE(notice_id, user_id) + ON CONFLICT DO NOTHING이라 몇 번을 불러도 행이 하나다."""
    user = await _login_member(client, db_session, "member-twice@example.com")
    notice = await _add_notice(db_session)

    assert (await client.post(f"/api/notices/{notice.id}/read")).status_code == 200
    assert (await client.post(f"/api/notices/{notice.id}/read")).status_code == 200

    result = await db_session.execute(
        select(func.count())
        .select_from(NoticeRead)
        .where(NoticeRead.notice_id == notice.id, NoticeRead.user_id == user.id)
    )
    assert result.scalar_one() == 1


async def test_mark_read_on_draft_returns_404(client, db_session):
    await _login_member(client, db_session, "member-read-draft@example.com")
    draft = await _add_notice(db_session, status=NoticeStatus.DRAFT, starts_at=None)

    resp = await client.post(f"/api/notices/{draft.id}/read")
    assert resp.status_code == 404


async def test_other_users_read_does_not_leak(client, db_session):
    """다른 사용자가 읽어도 내 is_read는 False로 남는다."""
    other = await _login_member(client, db_session, "member-other@example.com")
    notice = await _add_notice(db_session)
    assert (await client.post(f"/api/notices/{notice.id}/read")).status_code == 200

    await _login_member(client, db_session, "member-mine@example.com")
    listed = await client.get("/api/notices")
    row = next(r for r in listed.json() if r["id"] == notice.id)
    assert row["is_read"] is False
    assert other.id is not None


async def test_unread_count_counts_only_visible_unread(client, db_session):
    await _login_member(client, db_session, "member-count@example.com")
    now = now_local()

    await _add_notice(db_session, title="안읽음1")
    await _add_notice(db_session, title="안읽음2")
    await _add_notice(db_session, title="임시저장", status=NoticeStatus.DRAFT, starts_at=None)
    await _add_notice(db_session, title="예약", starts_at=now + timedelta(days=1))

    resp = await client.get("/api/notices/unread/count")
    assert resp.status_code == 200
    assert resp.json() == {"count": 2}


async def test_unread_count_drops_after_read(client, db_session):
    await _login_member(client, db_session, "member-count-read@example.com")
    notice = await _add_notice(db_session)

    assert (await client.get("/api/notices/unread/count")).json()["count"] == 1
    await client.post(f"/api/notices/{notice.id}/read")
    assert (await client.get("/api/notices/unread/count")).json()["count"] == 0


async def test_popups_return_only_popup_yn_y(client, db_session):
    await _login_member(client, db_session, "member-popup@example.com")

    await _add_notice(db_session, title="팝업아님", popup_yn=YN.N)
    popup = await _add_notice(db_session, title="팝업", popup_yn=YN.Y)

    resp = await client.get("/api/notices/popups")
    assert resp.status_code == 200
    assert [row["id"] for row in resp.json()] == [popup.id]
    assert resp.json()[0]["body"] == "본문"


async def test_popups_ignore_read_state(client, db_session):
    """팝업 닫기는 읽음과 무관하다 — 읽은 공지도 팝업 대상에서 빠지지 않는다."""
    await _login_member(client, db_session, "member-popup-read@example.com")
    popup = await _add_notice(db_session, popup_yn=YN.Y)
    await client.post(f"/api/notices/{popup.id}/read")

    resp = await client.get("/api/notices/popups")
    assert [row["id"] for row in resp.json()] == [popup.id]


async def test_popups_exclude_expired(client, db_session):
    await _login_member(client, db_session, "member-popup-expired@example.com")
    now = now_local()

    await _add_notice(
        db_session,
        popup_yn=YN.Y,
        starts_at=now - timedelta(days=3),
        ends_at=now - timedelta(days=1),
    )

    resp = await client.get("/api/notices/popups")
    assert resp.json() == []


async def test_draft_with_past_start_is_hidden_everywhere(client, db_session):
    """이 테스트가 없으면 네 쿼리의 `status = 'PUBLISHED'` 조건은 어떤 테스트에도
    걸리지 않는다 — _resolve_period가 임시저장의 starts_at을 항상 비우기 때문에
    'DRAFT면서 starts_at이 과거'인 조합은 API로는 만들어지지 않는다. ORM으로 직접
    그 조합을 만들어 네 조회 경로 모두에서 실제로 막히는지 확인한다."""
    await _login_member(client, db_session, "member-draft-past@example.com")
    now = now_local()

    draft = await _add_notice(
        db_session,
        title="임시저장인데시작일지남",
        status=NoticeStatus.DRAFT,
        starts_at=now - timedelta(days=1),
        popup_yn=YN.Y,
    )

    listed = await client.get("/api/notices")
    assert draft.title not in [row["title"] for row in listed.json()]

    count = await client.get("/api/notices/unread/count")
    assert count.json() == {"count": 0}

    popups = await client.get("/api/notices/popups")
    assert popups.json() == []

    resp = await client.post(f"/api/notices/{draft.id}/read")
    assert resp.status_code == 404


async def test_marking_notice_as_read_is_not_recorded(client, db_session):
    """읽음 표시는 목록을 열 때마다 발생한다 — 기록하면 다른 모든 행위를 덮는다."""
    await _login_member(client, db_session, "member-read-audit@example.com")
    notice = await _add_notice(db_session)

    resp = await client.post(f"/api/notices/{notice.id}/read")
    assert resp.status_code in (200, 201, 204)

    # count == 0은 로그인까지 포함해 센다 — 이 파일은 client 픽스처로 로그인하므로
    # LOGIN_SUCCESS 한 건이 잡힐 수 있다. 그건 이 테스트가 보려는 대상이 아니라 제외한다.
    conn = await raw_connection(db_session)
    count = await conn.fetchval(
        "SELECT COUNT(*) FROM audit_logs WHERE action != 'LOGIN_SUCCESS'"
    )
    assert count == 0
