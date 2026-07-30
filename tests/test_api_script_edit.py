"""대본 수정 — PUT /api/projects/{id}/stages/script"""

from contextlib import asynccontextmanager

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


async def _drain(db_session, stage_id: int):
    """API는 큐에 넣기만 한다. 테스트에서는 워커를 직접 한 번 돌려 완료시킨다."""
    from app.core.worker import StageWorker

    @asynccontextmanager
    async def _factory():
        yield db_session

    await StageWorker(session_factory=_factory).run_one(stage_id)


async def _project_in_review(client, db_session, topic: str = "제주도") -> int:
    """script 단계가 NEEDS_REVIEW인 프로젝트를 만든다(수정이 가능한 유일한 상태)."""
    pid = (
        await client.post("/api/projects", json={"title": "t", "topic": topic})
    ).json()["project"]["id"]
    ran = await client.post(f"/api/projects/{pid}/stages/script/run")
    assert ran.status_code == 202
    conn = await raw_connection(db_session)
    stage = await queries.find_stage(conn, project_id=pid, name="script")
    await _drain(db_session, stage["id"])
    return pid


async def _script_of(client, pid: int) -> dict:
    detail = (await client.get(f"/api/projects/{pid}")).json()
    return next(s for s in detail["stages"] if s["name"] == "script")


async def _set_stage_status(db_session, pid: int, status: str) -> None:
    conn = await raw_connection(db_session)
    stage = await queries.find_stage(conn, project_id=pid, name="script")
    await queries.update_stage_status(
        conn, id=stage["id"], status=status, updated_at=now_local(), updated_by=None
    )
    await db_session.commit()


_EDIT = {
    "title": "고친 제목",
    "hook": "고친 훅",
    "scenes": [
        {"narration": "첫 번째 나레이션", "on_screen": "화면1"},
        {"narration": "두 번째 나레이션", "on_screen": "화면2"},
    ],
}


async def test_save_returns_updated_script(client, db_session):
    await _login(client, db_session, "se1@example.com")
    pid = await _project_in_review(client, db_session)

    resp = await client.put(f"/api/projects/{pid}/stages/script", json=_EDIT)
    assert resp.status_code == 200

    script = next(s for s in resp.json()["stages"] if s["name"] == "script")
    assert script["output"]["title"] == "고친 제목"
    assert script["output"]["hook"] == "고친 훅"
    assert [s["narration"] for s in script["output"]["scenes"]] == [
        "첫 번째 나레이션",
        "두 번째 나레이션",
    ]


async def test_edited_narration_reaches_the_tts(client, db_session, monkeypatch, tmp_path):
    """이 기능이 실제로 뜻이 있는지를 보는 테스트.

    대본을 고쳐 저장하고 승인한 뒤 음성 단계를 돌려서, TTS에 들어간 텍스트가
    수정본인지 확인한다. fake voice provider는 낭독 텍스트를 파일에 그대로 적는다.
    """
    from app.utils import storage

    monkeypatch.setattr(storage, "_root", lambda: tmp_path)

    await _login(client, db_session, "se2@example.com")
    pid = await _project_in_review(client, db_session)

    assert (await client.put(f"/api/projects/{pid}/stages/script", json=_EDIT)).status_code == 200
    assert (await client.post(f"/api/projects/{pid}/stages/script/approve")).status_code == 200

    conn = await raw_connection(db_session)
    voice = await queries.find_stage(conn, project_id=pid, name="voice")
    await client.post(f"/api/projects/{pid}/stages/voice/run")
    await _drain(db_session, voice["id"])

    written = (tmp_path / f"projects/{pid}/voice/voice.mp3").read_text(encoding="utf-8")
    assert "첫 번째 나레이션 두 번째 나레이션" in written
    # AI 초안의 문구는 더 이상 읽히지 않는다.
    assert "핵심 포인트입니다" not in written


async def test_save_keeps_status_and_attempt(client, db_session):
    """수정은 상태 전이가 아니다 — 저장 후에도 승인 대기이고, 재생성 seed도 그대로다."""
    await _login(client, db_session, "se3@example.com")
    pid = await _project_in_review(client, db_session)
    before = await _script_of(client, pid)

    assert (await client.put(f"/api/projects/{pid}/stages/script", json=_EDIT)).status_code == 200

    after = await _script_of(client, pid)
    assert after["status"] == StageStatus.NEEDS_REVIEW
    assert after["attempt"] == before["attempt"]


async def test_scene_removal_is_reflected(client, db_session):
    await _login(client, db_session, "se4@example.com")
    pid = await _project_in_review(client, db_session)
    assert len((await _script_of(client, pid))["output"]["scenes"]) == 3

    one = {"title": "t", "hook": "h", "scenes": [{"narration": "하나만", "on_screen": ""}]}
    assert (await client.put(f"/api/projects/{pid}/stages/script", json=one)).status_code == 200

    scenes = (await _script_of(client, pid))["output"]["scenes"]
    assert len(scenes) == 1
    assert scenes[0]["narration"] == "하나만"


async def test_scene_addition_is_reflected(client, db_session):
    await _login(client, db_session, "se5@example.com")
    pid = await _project_in_review(client, db_session)

    five = {
        "title": "t",
        "hook": "h",
        "scenes": [{"narration": f"장면 {i}", "on_screen": ""} for i in range(1, 6)],
    }
    assert (await client.put(f"/api/projects/{pid}/stages/script", json=five)).status_code == 200

    scenes = (await _script_of(client, pid))["output"]["scenes"]
    assert len(scenes) == 5


async def test_order_is_taken_from_the_array_and_index_renumbered(client, db_session):
    await _login(client, db_session, "se6@example.com")
    pid = await _project_in_review(client, db_session)

    reordered = {
        "title": "t",
        "hook": "h",
        "scenes": [
            {"narration": "나중이었던 것", "on_screen": ""},
            {"narration": "먼저였던 것", "on_screen": ""},
        ],
    }
    resp = await client.put(f"/api/projects/{pid}/stages/script", json=reordered)
    assert resp.status_code == 200

    scenes = (await _script_of(client, pid))["output"]["scenes"]
    assert [s["narration"] for s in scenes] == ["나중이었던 것", "먼저였던 것"]
    assert [s["index"] for s in scenes] == [1, 2]


async def test_duration_is_recomputed(client, db_session):
    """AI가 낸 45초가 그대로 남지 않는다 — 장면을 줄이면 값도 줄어야 한다."""
    await _login(client, db_session, "se7@example.com")
    pid = await _project_in_review(client, db_session)
    assert (await _script_of(client, pid))["output"]["estimated_duration_sec"] == 45

    short = {"title": "t", "hook": "h", "scenes": [{"narration": "짧게", "on_screen": ""}]}
    assert (await client.put(f"/api/projects/{pid}/stages/script", json=short)).status_code == 200

    assert (await _script_of(client, pid))["output"]["estimated_duration_sec"] < 45


async def test_blank_on_screen_is_accepted(client, db_session):
    """on_screen은 비어도 스톡 검색이 topic으로 폴백하므로 막지 않는다."""
    await _login(client, db_session, "se8@example.com")
    pid = await _project_in_review(client, db_session)

    body = {"title": "t", "hook": "h", "scenes": [{"narration": "나레이션", "on_screen": ""}]}
    assert (await client.put(f"/api/projects/{pid}/stages/script", json=body)).status_code == 200


async def test_blank_hook_is_accepted(client, db_session):
    await _login(client, db_session, "se9@example.com")
    pid = await _project_in_review(client, db_session)

    body = {"title": "t", "hook": "", "scenes": [{"narration": "나레이션", "on_screen": ""}]}
    assert (await client.put(f"/api/projects/{pid}/stages/script", json=body)).status_code == 200


async def test_zero_scenes_is_422(client, db_session):
    """장면이 없으면 TTS가 빈 문자열을 읽는다."""
    await _login(client, db_session, "se10@example.com")
    pid = await _project_in_review(client, db_session)

    body = {"title": "t", "hook": "h", "scenes": []}
    assert (await client.put(f"/api/projects/{pid}/stages/script", json=body)).status_code == 422


async def test_blank_narration_is_422(client, db_session):
    await _login(client, db_session, "se11@example.com")
    pid = await _project_in_review(client, db_session)

    body = {"title": "t", "hook": "h", "scenes": [{"narration": "   ", "on_screen": "x"}]}
    assert (await client.put(f"/api/projects/{pid}/stages/script", json=body)).status_code == 422


async def test_blank_title_is_422(client, db_session):
    await _login(client, db_session, "se12@example.com")
    pid = await _project_in_review(client, db_session)

    body = {"title": "  ", "hook": "h", "scenes": [{"narration": "나레이션", "on_screen": ""}]}
    assert (await client.put(f"/api/projects/{pid}/stages/script", json=body)).status_code == 422


async def test_too_many_scenes_is_422(client, db_session):
    await _login(client, db_session, "se13@example.com")
    pid = await _project_in_review(client, db_session)

    body = {
        "title": "t",
        "hook": "h",
        "scenes": [{"narration": f"장면 {i}", "on_screen": ""} for i in range(21)],
    }
    assert (await client.put(f"/api/projects/{pid}/stages/script", json=body)).status_code == 422


async def test_total_narration_too_long_is_422(client, db_session):
    await _login(client, db_session, "se14@example.com")
    pid = await _project_in_review(client, db_session)

    body = {
        "title": "t",
        "hook": "h",
        "scenes": [{"narration": "가" * 1001, "on_screen": ""} for _ in range(5)],
    }
    assert (await client.put(f"/api/projects/{pid}/stages/script", json=body)).status_code == 422


async def test_states_other_than_needs_review_are_409(client, db_session):
    """승인된 대본을 덮어쓰면 이미 만들어진 음성과 어긋난다 — DB CAS가 막는다."""
    await _login(client, db_session, "se15@example.com")

    for status in (
        StageStatus.PENDING,
        StageStatus.RUNNING,
        StageStatus.APPROVED,
        StageStatus.FAILED,
    ):
        pid = await _project_in_review(client, db_session)
        original = (await _script_of(client, pid))["output"]
        await _set_stage_status(db_session, pid, status)

        resp = await client.put(f"/api/projects/{pid}/stages/script", json=_EDIT)
        assert resp.status_code == 409, f"{status}에서 409여야 한다"
        assert resp.json()["code"] == "STAGE_CONFLICT"

        await _set_stage_status(db_session, pid, StageStatus.NEEDS_REVIEW)
        assert (await _script_of(client, pid))["output"] == original, "거절했으면 내용도 그대로"


async def test_project_without_script_stage_is_404(client, db_session):
    await _login(client, db_session, "se16@example.com")
    pid = (
        await client.post("/api/projects", json={"title": "t", "topic": "주제"})
    ).json()["project"]["id"]
    conn = await raw_connection(db_session)
    stage = await queries.find_stage(conn, project_id=pid, name="script")
    await conn.execute("DELETE FROM stages WHERE id = $1", stage["id"])
    await db_session.commit()

    assert (await client.put(f"/api/projects/{pid}/stages/script", json=_EDIT)).status_code == 404


async def test_other_users_project_is_404_and_unchanged(client, db_session):
    await _login(client, db_session, "se17-owner@example.com")
    pid = await _project_in_review(client, db_session)
    original = (await _script_of(client, pid))["output"]

    client.cookies.clear()
    await _login(client, db_session, "se17-other@example.com")
    assert (await client.put(f"/api/projects/{pid}/stages/script", json=_EDIT)).status_code == 404

    client.cookies.clear()
    await _login(client, db_session, "se17-owner2@example.com")  # 소유자가 아니어도 확인은 DB로
    conn = await raw_connection(db_session)
    stage = await queries.find_stage(conn, project_id=pid, name="script")
    from app.core.pipeline import decode_stage

    assert decode_stage(dict(stage))["output"] == original


async def test_admin_cannot_edit_others_script(client, db_session):
    """관리자는 열람만 한다 — 다른 쓰기 경로와 같은 경계다."""
    await _login(client, db_session, "se18-owner@example.com")
    pid = await _project_in_review(client, db_session)

    client.cookies.clear()
    await _login(client, db_session, "se18-admin@example.com", role=UserRole.ADMIN)
    assert (await client.put(f"/api/projects/{pid}/stages/script", json=_EDIT)).status_code == 404


async def test_requires_auth(client):
    assert (await client.put("/api/projects/1/stages/script", json=_EDIT)).status_code == 401
