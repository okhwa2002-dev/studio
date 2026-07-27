from app.auth.security import hash_password
from app.constants import ProjectStatus, StageStatus, UserRole, UserStatus
from app.models.project import Project
from app.models.stage import Stage
from app.models.user import User
from app.utils.time import now_local


async def _login(client, db_session, email: str, role: str = UserRole.MEMBER) -> User:
    user = User(email=email, password_hash=hash_password("pw12345678"),
                role=role, status=UserStatus.ACTIVE, name="홍길동")
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    resp = await client.post("/api/auth/login", json={"email": email, "password": "pw12345678"})
    assert resp.status_code == 200
    return user


async def _project(db_session, owner_id: int, status: str, stage_status: str) -> Project:
    now = now_local()
    project = Project(owner_id=owner_id, title="t", topic="주제", status=status,
                      created_at=now, updated_at=now)
    db_session.add(project)
    await db_session.commit()
    await db_session.refresh(project)
    db_session.add(Stage(project_id=project.id, name="script", provider="fake",
                         status=stage_status, created_at=now, updated_at=now))
    await db_session.commit()
    return project


async def test_dashboard_requires_auth(client):
    resp = await client.get("/api/dashboard/summary")
    assert resp.status_code == 401


async def test_dashboard_summary_member(client, db_session):
    user = await _login(client, db_session, "dash-member@example.com")
    await _project(db_session, user.id, ProjectStatus.DRAFT, StageStatus.FAILED)
    await _project(db_session, user.id, ProjectStatus.DONE, StageStatus.APPROVED)

    resp = await client.get("/api/dashboard/summary")
    assert resp.status_code == 200
    body = resp.json()

    assert body["projects"] == {"total": 2, "draft": 1, "review": 0, "done": 1}
    # 실패 단계가 있는 DRAFT 프로젝트만 "조치 필요"에 잡힌다.
    assert len(body["attention"]) == 1
    assert body["attention"][0]["failed"] is True
    assert body["attention"][0]["needs_review"] is False
    assert body["attention"][0]["current_stage"] == "script"  # 생성 시 기본 단계
    # 멤버 응답에는 운영 지표가 없다.
    assert body["admin"] is None


async def test_dashboard_summary_admin(client, db_session):
    admin = await _login(client, db_session, "dash-admin@example.com", role=UserRole.ADMIN)
    # 승인 대기 사용자와 잠긴 사용자를 하나씩 만든다.
    db_session.add(User(email="pending@example.com", password_hash=hash_password("pw12345678"),
                        status=UserStatus.PENDING, name="대기"))
    db_session.add(User(email="locked@example.com", password_hash=hash_password("pw12345678"),
                        status=UserStatus.ACTIVE, name="잠김", locked_at=now_local()))
    await db_session.commit()
    # 검토 필요 단계를 가진 관리자 소유 프로젝트 하나.
    await _project(db_session, admin.id, ProjectStatus.REVIEW, StageStatus.NEEDS_REVIEW)

    resp = await client.get("/api/dashboard/summary")
    assert resp.status_code == 200
    admin_block = resp.json()["admin"]
    assert admin_block is not None
    assert admin_block["users"]["pending"] == 1
    assert admin_block["users"]["locked"] == 1
    assert admin_block["users"]["active"] >= 2  # 관리자 본인 + 잠긴(ACTIVE) 사용자
    assert admin_block["projects"]["review"] == 1
    assert admin_block["stages"]["needs_review"] == 1
