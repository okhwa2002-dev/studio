import pytest
from starlette.datastructures import Headers
from starlette.requests import Request

from app.auth.security import hash_password
from app.constants import UserRole, UserStatus, AuditAction, AuditTarget
from app.core import audit
from app.db import raw_connection
from app.models.user import User


async def _user(db_session, email: str = "actor@example.com") -> dict:
    user = User(
        email=email,
        password_hash=hash_password("pw12345"),
        role=UserRole.MEMBER,
        status=UserStatus.ACTIVE,
        name="홍길동",
    )
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    # current_user가 넘겨주는 모양(dict)을 그대로 흉내낸다.
    return {"id": user.id, "email": user.email, "name": user.name}


def _request(method: str = "POST", path: str = "/api/projects/12", ip: str = "10.0.0.9") -> Request:
    """실제 요청 없이 Request를 만든다. 헬퍼가 읽는 세 값만 채우면 충분하다."""
    scope = {
        "type": "http",
        "method": method,
        "path": path,
        "raw_path": path.encode(),
        "query_string": b"",
        "headers": Headers({}).raw,
        "client": (ip, 12345),
        "scheme": "http",
        "server": ("test", 80),
    }
    return Request(scope)


async def _last_row(db_session):
    conn = await raw_connection(db_session)
    return await conn.fetchrow("SELECT * FROM audit_logs ORDER BY id DESC LIMIT 1")


async def _count(db_session) -> int:
    conn = await raw_connection(db_session)
    return await conn.fetchval("SELECT COUNT(*) FROM audit_logs")


async def test_record_fills_actor_snapshot(db_session):
    actor = await _user(db_session)
    conn = await raw_connection(db_session)

    await audit.record(conn, action=AuditAction.LOGIN_SUCCESS, actor=actor)

    row = await _last_row(db_session)
    assert row["action"] == "LOGIN_SUCCESS"
    assert row["actor_id"] == actor["id"]
    assert row["actor_email"] == "actor@example.com"
    assert row["actor_name"] == "홍길동"
    assert row["success_yn"] == "Y"
    assert row["created_at"] is not None


async def test_record_fills_request_columns(db_session):
    actor = await _user(db_session)
    conn = await raw_connection(db_session)

    await audit.record(
        conn,
        action=AuditAction.PROJECT_DELETE,
        request=_request("DELETE", "/api/projects/12", "10.0.0.9"),
        actor=actor,
        target_type=AuditTarget.PROJECT,
        target_id=12,
        target_label="여행 브이로그",
        summary="프로젝트 삭제 (30일 후 완전 삭제)",
    )

    row = await _last_row(db_session)
    assert row["http_method"] == "DELETE"
    assert row["http_path"] == "/api/projects/12"
    assert row["actor_ip"] == "10.0.0.9"
    assert row["target_type"] == "PROJECT"
    assert row["target_id"] == 12
    assert row["target_label"] == "여행 브이로그"


async def test_record_without_request_leaves_http_columns_null(db_session):
    """요청 밖(정리 잡 등)에서도 부를 수 있어야 한다."""
    conn = await raw_connection(db_session)

    await audit.record(conn, action=AuditAction.LOGIN_FAILURE, actor_email="x@y.com", success=False)

    row = await _last_row(db_session)
    assert row["http_method"] is None
    assert row["http_path"] is None
    assert row["actor_ip"] is None


async def test_record_without_actor_keeps_email_only(db_session):
    """없는 계정으로 로그인 시도 — 계정은 특정 못 해도 입력 이메일은 남는다."""
    conn = await raw_connection(db_session)

    await audit.record(
        conn, action=AuditAction.LOGIN_FAILURE, actor_email="ghost@example.com", success=False
    )

    row = await _last_row(db_session)
    assert row["actor_id"] is None
    assert row["actor_email"] == "ghost@example.com"
    assert row["actor_name"] is None
    assert row["success_yn"] == "N"


async def test_long_summary_is_clipped(db_session):
    conn = await raw_connection(db_session)

    await audit.record(conn, action=AuditAction.SYSTEM_SETTINGS_UPDATE, summary="가" * 500)

    row = await _last_row(db_session)
    assert len(row["summary"]) == 200


async def test_long_target_label_is_clipped(db_session):
    conn = await raw_connection(db_session)

    await audit.record(conn, action=AuditAction.PROJECT_CREATE, target_label="제" * 400)

    row = await _last_row(db_session)
    assert len(row["target_label"]) == 200


async def test_record_is_rolled_back_with_the_transaction(db_session):
    """record는 원 작업과 같은 트랜잭션이다 — 작업이 롤백되면 기록도 사라진다."""
    conn = await raw_connection(db_session)
    await audit.record(conn, action=AuditAction.LOGIN_SUCCESS, actor_email="a@b.com")

    await db_session.rollback()

    assert await _count(db_session) == 0


async def test_record_failure_survives_rollback(db_session):
    """record_failure는 즉시 커밋한다 — 예외로 끝나는 경로에서도 기록이 남는다.

    별도 세션 조회로는 확인할 수 없다(conftest의 SAVEPOINT 격리 때문에 커밋된 행도
    바깥에서는 안 보인다). 롤백 후 살아남는지가 커밋 여부를 가르는 유일한 신호다.
    """
    await audit.record_failure(
        db_session, action=AuditAction.LOGIN_FAILURE, actor_email="ghost@example.com", success=False
    )

    await db_session.rollback()

    assert await _count(db_session) == 1
