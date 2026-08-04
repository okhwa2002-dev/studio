from datetime import timedelta

from app.auth.security import hash_password
from app.constants import YN, AuditAction, AuditTarget, UserRole, UserStatus
from app.db import raw_connection
from app.models.audit_log import AuditLog
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


async def _seed(db_session, **overrides) -> AuditLog:
    values = {
        "action": AuditAction.PROJECT_CREATE,
        "actor_email": "member@example.com",
        "actor_name": "홍길동",
        "target_type": AuditTarget.PROJECT,
        "target_id": 1,
        "target_label": "여행 브이로그",
        "success_yn": YN.Y,
        "summary": "프로젝트 생성",
        "created_at": now_local(),
    }
    values.update(overrides)
    log = AuditLog(**values)
    db_session.add(log)
    await db_session.commit()
    return log


async def _list(client, **params) -> dict:
    query = "&".join(f"{k}={v}" for k, v in params.items())
    resp = await client.get(f"/api/admin/audit-logs?{query}" if query else "/api/admin/audit-logs")
    assert resp.status_code == 200, resp.text
    return resp.json()


async def test_default_window_is_last_seven_days(client, db_session):
    await _login(client, db_session, "logs-window@example.com")
    await _seed(db_session, summary="최근")
    await _seed(db_session, summary="오래됨", created_at=now_local() - timedelta(days=8))

    data = await _list(client)

    summaries = [r["summary"] for r in data["items"]]
    assert "최근" in summaries
    assert "오래됨" not in summaries


async def test_explicit_range_includes_older_rows(client, db_session):
    await _login(client, db_session, "logs-range@example.com")
    old = now_local() - timedelta(days=20)
    await _seed(db_session, summary="오래됨", created_at=old)

    data = await _list(client, **{"from": old.date().isoformat(), "to": now_local().date().isoformat()})

    assert "오래됨" in [r["summary"] for r in data["items"]]


async def test_range_includes_the_whole_end_day(client, db_session):
    """to는 그날 23:59:59까지 포함해야 한다 — 오늘 오후의 기록이 빠지면 안 된다."""
    await _login(client, db_session, "logs-endday@example.com")
    today = now_local()
    await _seed(db_session, summary="오늘늦게", created_at=today.replace(hour=23, minute=50))

    data = await _list(client, **{"from": today.date().isoformat(), "to": today.date().isoformat()})

    assert "오늘늦게" in [r["summary"] for r in data["items"]]


async def test_action_filter(client, db_session):
    await _login(client, db_session, "logs-action@example.com")
    await _seed(db_session, action=AuditAction.PROJECT_CREATE, summary="생성")
    await _seed(db_session, action=AuditAction.PROJECT_DELETE, summary="삭제")

    data = await _list(client, action="PROJECT_DELETE")

    assert [r["summary"] for r in data["items"]] == ["삭제"]


async def test_success_filter(client, db_session):
    await _login(client, db_session, "logs-success@example.com")
    await _seed(db_session, summary="성공건", success_yn=YN.Y)
    await _seed(db_session, summary="실패건", success_yn=YN.N, action=AuditAction.LOGIN_FAILURE)

    data = await _list(client, success="N")

    assert [r["summary"] for r in data["items"]] == ["실패건"]


async def test_query_matches_each_of_four_columns(client, db_session):
    await _login(client, db_session, "logs-q@example.com")
    await _seed(db_session, actor_email="needle1@example.com", summary="a")
    await _seed(db_session, actor_name="니들둘", summary="b")
    await _seed(db_session, target_label="니들셋 프로젝트", summary="c")
    await _seed(db_session, summary="니들넷 요약")

    assert [r["summary"] for r in (await _list(client, q="needle1"))["items"]] == ["a"]
    assert [r["summary"] for r in (await _list(client, q="니들둘"))["items"]] == ["b"]
    assert [r["summary"] for r in (await _list(client, q="니들셋"))["items"]] == ["c"]
    assert [r["summary"] for r in (await _list(client, q="니들넷"))["items"]] == ["니들넷 요약"]


async def test_pagination_splits_without_overlap(client, db_session):
    admin = await _login(client, db_session, "logs-page@example.com")
    for i in range(5):
        await _seed(db_session, summary=f"기록{i}")

    first = await _list(client, size=2, page=1)
    second = await _list(client, size=2, page=2)

    # 로그인도 한 건 기록되므로 total은 6이다.
    assert first["total"] == 6
    assert first["page"] == 1 and first["size"] == 2
    assert len(first["items"]) == 2
    assert {r["id"] for r in first["items"]} & {r["id"] for r in second["items"]} == set()


async def test_sorted_newest_first(client, db_session):
    await _login(client, db_session, "logs-sort@example.com")
    await _seed(db_session, summary="먼저", created_at=now_local() - timedelta(hours=2))
    await _seed(db_session, summary="나중", created_at=now_local() - timedelta(hours=1))

    data = await _list(client)

    summaries = [r["summary"] for r in data["items"]]
    assert summaries.index("나중") < summaries.index("먼저")


async def test_size_over_limit_is_422(client, db_session):
    await _login(client, db_session, "logs-size@example.com")

    resp = await client.get("/api/admin/audit-logs?size=201")
    assert resp.status_code == 422


async def test_reversed_range_is_422(client, db_session):
    await _login(client, db_session, "logs-reversed@example.com")

    resp = await client.get("/api/admin/audit-logs?from=2026-07-30&to=2026-07-01")
    assert resp.status_code == 422
    assert resp.json()["code"] == "VALIDATION_ERROR"


async def test_unknown_action_is_422(client, db_session):
    await _login(client, db_session, "logs-badaction@example.com")

    resp = await client.get("/api/admin/audit-logs?action=NOPE")
    assert resp.status_code == 422


async def test_member_is_forbidden(client, db_session):
    await _login(client, db_session, "logs-member@example.com", role=UserRole.MEMBER)

    resp = await client.get("/api/admin/audit-logs")
    assert resp.status_code == 403


async def test_anonymous_is_unauthorized(client):
    resp = await client.get("/api/admin/audit-logs")
    assert resp.status_code == 401


async def test_empty_result_is_200_with_zero_total(client, db_session):
    await _login(client, db_session, "logs-empty@example.com")

    data = await _list(client, q="존재하지않는검색어")

    assert data["items"] == []
    assert data["total"] == 0


async def test_default_size_matches_screen_default(client, db_session):
    """size를 생략하면 목록 화면 공통 기본값(20)과 같은 값으로 답한다.

    프론트는 언제나 size를 보내므로 실동작은 이 값에 걸리지 않는다. 그래도 맞춰 두는
    것은 /docs에 뜨는 기본값이 화면과 어긋나면 API만 보고 판단하는 사람이 틀리기
    때문이다.
    """
    await _login(client, db_session, "logs-default-size@example.com")
    await _seed(db_session)

    data = await _list(client)

    assert data["size"] == 20
