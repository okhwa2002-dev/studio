import asyncio
import json

import app.core.views as core_views
from app.api.projects import project_events
from app.auth.security import hash_password
from app.constants import UserRole, UserStatus
from app.core import events
from app.db import raw_connection
from app.models.user import User
from app.queries import queries


async def _login(client, db_session, email: str) -> User:
    user = User(email=email, password_hash=hash_password("pw12345"),
                role=UserRole.MEMBER, status=UserStatus.ACTIVE)
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    resp = await client.post("/api/auth/login", json={"email": email, "password": "pw12345"})
    assert resp.status_code == 200
    return user


async def _as_current_user(db_session, user_id: int) -> dict:
    """current_user 의존성과 동일한 조회로 페이로드를 만든다 — {"id": user_id}처럼 손으로
    흉내내면 current_user가 돌려주는 모양이 바뀔 때 조용히 어긋난다."""
    conn = await raw_connection(db_session)
    row = await queries.find_by_id(conn, id=user_id)
    user = dict(row)
    user.pop("password_hash", None)
    return user


def _parse(chunk: str) -> dict:
    assert chunk.startswith("data: ")
    return json.loads(chunk[len("data: "):])


async def test_events_requires_auth(client):
    # client.stream()이 아니라 client.get()으로 감싼다 — 인증 실패는 스트림이 열리기 전에
    # 예외로 끝나므로 일반 응답이라 get()이면 충분하고, 오너십 체크가 회귀해 진짜
    # StreamingResponse가 돌아오는 사고가 나도 wait_for가 있어 스위트 전체가 매달리는 대신
    # 이 한 테스트만 타임아웃으로 실패한다(ASGITransport는 소켓이 없어 자체 타임아웃이 없다).
    resp = await asyncio.wait_for(client.get("/api/projects/1/events"), timeout=5)
    assert resp.status_code == 401


async def test_events_rejects_other_owner(client, db_session):
    await _login(client, db_session, "sse-owner@example.com")
    pid = (await client.post("/api/projects", json={"title": "t", "topic": "비밀"})).json()["project"]["id"]
    await _login(client, db_session, "sse-intruder@example.com")
    resp = await asyncio.wait_for(client.get(f"/api/projects/{pid}/events"), timeout=5)
    assert resp.status_code == 404


async def test_events_sends_snapshot_then_published_event(client, db_session):
    # 이 테스트만 client.stream()이 아니라 라우트 함수를 직접 호출해 body_iterator를
    # 구동한다. httpx==0.28.1의 ASGITransport.handle_async_request()는
    # `await self.app(scope, receive, send)`가 완전히 끝나야(=StreamingResponse의
    # body_iterator가 StopAsyncIteration할 때까지) Response를 만든다
    # (.venv/Lib/site-packages/httpx/_transports/asgi.py:169-187). SSE는 끝나지
    # 않는 스트림이라 client.stream()으로는 이 흐름 자체를 테스트할 수 없다 — FastAPI/DB와
    # 무관한 최소 Starlette 앱으로 격리 재현해 확인했다(무한 제너레이터 스트림은
    # 클라이언트가 응답 상태코드조차 받지 못한 채 영원히 멈춘다).
    # 인증 401·소유자 404 케이스는 스트림 시작 전에 예외로 끝나므로 client.get()이
    # 정상 동작한다(위 두 테스트).
    #
    # 주의: project_events 안의 await db.close()가 이 db_session을 실제로 닫는다 —
    # client도 같은 세션을 쓰므로, 이 함수 안에서 이 지점 이후로 client.*를 호출하면
    # 세션이 이미 닫혀 있어 혼란스러운 에러가 난다. 이 테스트는 그 뒤로 client를 쓰지
    # 않으므로 안전하다.
    user = await _login(client, db_session, "sse@example.com")
    pid = (await client.post("/api/projects", json={"title": "t", "topic": "달"})).json()["project"]["id"]
    stage_id = (await client.get(f"/api/projects/{pid}")).json()["stages"][0]["id"]

    # 진행 중인 단계의 마지막 진행률이 id 키 → name 키로 올바르게 옮겨 실리는지 pin한다
    # (빈 dict만 확인하면 키 불일치도 통과해버린다).
    events.set_progress(stage_id, {"type": "progress", "stage": "script",
                                    "percent": 42.0, "message": "대본을 만드는 중…"})

    user_payload = await _as_current_user(db_session, user.id)
    resp = await project_events(pid, user=user_payload, db=db_session)
    assert resp.status_code == 200
    assert resp.media_type == "text/event-stream"
    assert resp.headers["cache-control"] == "no-cache"
    assert resp.headers["x-accel-buffering"] == "no"

    snapshot = _parse(await asyncio.wait_for(resp.body_iterator.__anext__(), timeout=5))
    assert snapshot["type"] == "snapshot"
    assert snapshot["project"]["id"] == pid
    assert snapshot["stages"][0]["name"] == "script"
    assert snapshot["progress"]["script"]["message"] == "대본을 만드는 중…"

    # 구독이 붙은 뒤(스냅샷을 이미 만든 뒤) 발행한 이벤트가 그대로 흘러나와야 한다.
    events.publish(pid, {"type": "progress", "stage": "script",
                         "percent": None, "message": "대본을 생성하는 중…"})
    pushed = _parse(await asyncio.wait_for(resp.body_iterator.__anext__(), timeout=5))
    assert pushed["message"] == "대본을 생성하는 중…"

    assert pid in events._subscribers  # 아직 연결이 열려 있으니 구독도 남아 있다
    await resp.body_iterator.aclose()  # 클라이언트 연결 종료 시뮬레이션
    assert pid not in events._subscribers  # finally에서 반드시 구독을 해제해야 한다


async def test_events_subscribe_before_snapshot_prevents_lost_event(client, db_session, monkeypatch):
    """Important #1 회귀 pin: 스냅샷을 만드는 바로 그 순간에 발행된 이벤트도 놓치면 안 된다.

    구독을 스냅샷보다 먼저 여는 게 핵심이므로, views.detail(스냅샷을 만드는 지점)을
    몽키패치해 그 순간에 이벤트를 발행시킨다. 구독이 먼저 열려 있어야만(=이 파일의
    project_events가 subscribe → snapshot 순서일 때만) 이 이벤트가 큐에 잡혀 다음
    __anext__로 전달된다. 순서가 스냅샷 → subscribe로 되돌아가면, 이 시점엔 아직 구독이
    존재하지 않아 이벤트가 그냥 버려지고, 다음 __anext__는 (핑도 없이) 5초 타임아웃으로
    "행"이 아니라 실패로 끝난다 — 아래에서 실제로 되돌려 확인했다(리포트 참조).
    """
    original_detail = core_views.detail

    async def _detail_then_publish(conn, project_id):
        result = await original_detail(conn, project_id)
        events.publish(project_id, {"type": "progress", "stage": "script",
                                     "percent": None, "message": "스냅샷을 만드는 도중 발행"})
        return result

    monkeypatch.setattr(core_views, "detail", _detail_then_publish)

    user = await _login(client, db_session, "sse-order@example.com")
    pid = (await client.post("/api/projects", json={"title": "t", "topic": "순서"})).json()["project"]["id"]
    user_payload = await _as_current_user(db_session, user.id)

    resp = await project_events(pid, user=user_payload, db=db_session)
    snapshot = _parse(await asyncio.wait_for(resp.body_iterator.__anext__(), timeout=5))
    assert snapshot["type"] == "snapshot"

    pushed = _parse(await asyncio.wait_for(resp.body_iterator.__anext__(), timeout=5))
    assert pushed["message"] == "스냅샷을 만드는 도중 발행"

    await resp.body_iterator.aclose()


async def test_events_sends_ping_on_timeout(client, db_session, monkeypatch):
    # ping 간격을 몽키패치해 15초를 기다리지 않고도 except TimeoutError 분기를 결정적으로 친다.
    from app.api import projects as projects_module

    monkeypatch.setattr(projects_module, "_PING_INTERVAL_SEC", 0.05)

    user = await _login(client, db_session, "sse-ping@example.com")
    pid = (await client.post("/api/projects", json={"title": "t", "topic": "핑"})).json()["project"]["id"]
    user_payload = await _as_current_user(db_session, user.id)

    resp = await project_events(pid, user=user_payload, db=db_session)
    await asyncio.wait_for(resp.body_iterator.__anext__(), timeout=5)  # 스냅샷은 건너뛴다

    ping = await asyncio.wait_for(resp.body_iterator.__anext__(), timeout=5)
    assert ping == ": ping\n\n"

    await resp.body_iterator.aclose()
