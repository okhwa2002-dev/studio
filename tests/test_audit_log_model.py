from app.constants import YN, AuditAction, AuditTarget
from app.models.audit_log import AuditLog
from app.utils.time import now_local


async def test_insert_and_read_back(db_session):
    log = AuditLog(
        action=AuditAction.PROJECT_DELETE,
        actor_id=None,
        actor_email="user@example.com",
        actor_name="홍길동",
        actor_ip="127.0.0.1",
        target_type=AuditTarget.PROJECT,
        target_id=12,
        target_label="여행 브이로그",
        http_method="DELETE",
        http_path="/api/projects/12",
        success_yn=YN.Y,
        summary="프로젝트 삭제 (30일 후 완전 삭제)",
        created_at=now_local(),
    )
    db_session.add(log)
    await db_session.commit()
    await db_session.refresh(log)

    assert log.id is not None
    assert log.action == "PROJECT_DELETE"
    assert log.success_yn == "Y"


async def test_optional_columns_default_to_none(db_session):
    """요청 밖에서 남길 사건을 위해 http_*·target_*은 비어 있어도 저장된다."""
    log = AuditLog(action=AuditAction.LOGIN_FAILURE, success_yn=YN.N, created_at=now_local())
    db_session.add(log)
    await db_session.commit()
    await db_session.refresh(log)

    assert log.actor_id is None
    assert log.http_path is None
    assert log.target_type is None
