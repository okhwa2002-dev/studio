import asyncio
import json

from fastapi import APIRouter, Depends
from fastapi.responses import FileResponse, StreamingResponse
from pydantic import BaseModel, field_validator
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import current_user
from app.config import get_settings
from app.constants import AssetKind, ProjectStatus, StageName, StageStatus
from app.core import events, pipeline, views
from app.core.worker import get_worker
from app.db import get_db, raw_connection
from app.queries import queries
from app.utils import storage
from app.utils.errors import AppError, Errors
from app.utils.time import now_local

router = APIRouter(prefix="/projects", tags=["projects"])


async def _load_owned_project(conn, project_id: int, user_id: int) -> dict:
    row = await queries.find_project_by_id(conn, id=project_id)
    if row is None or row["owner_id"] != user_id:
        raise Errors.not_found("프로젝트를 찾을 수 없습니다.")
    return pipeline.decode_stage(row)  # settings jsonb 디코드


async def _load_stage(conn, project_id: int, name: str) -> dict:
    row = await queries.find_stage(conn, project_id=project_id, name=name)
    if row is None:
        raise Errors.not_found("단계를 찾을 수 없습니다.")
    return pipeline.decode_stage(row)  # output jsonb 디코드


class CreateProjectRequest(BaseModel):
    title: str
    topic: str
    auto_run: bool = False  # 켜면 검토 없이 4단계를 끝까지 진행한다

    @field_validator("title", "topic")
    @classmethod
    def _not_blank(cls, v: str) -> str:
        # 앞뒤 공백을 다듬고, 공백뿐인 값은 거부한다(→ FastAPI가 422로 응답).
        v = v.strip()
        if not v:
            raise ValueError("빈 값일 수 없습니다.")
        return v


@router.post("", status_code=201)
async def create_project(
    body: CreateProjectRequest,
    user: dict = Depends(current_user),
    db: AsyncSession = Depends(get_db),
):
    conn = await raw_connection(db)
    now = now_local()
    project_id = await queries.insert_project(
        conn, owner_id=user["id"], title=body.title, topic=body.topic,
        status=ProjectStatus.DRAFT, current_stage=StageName.SCRIPT,
        settings=json.dumps({"auto_run": body.auto_run}),
        created_at=now, updated_at=now, created_by=user["id"], updated_by=user["id"],
    )
    stage_id = await queries.insert_stage(
        conn, project_id=project_id, name=StageName.SCRIPT, provider=get_settings().script_provider,
        status=StageStatus.PENDING, output=json.dumps({}), error=None, attempt=0,
        started_at=None, finished_at=None,
        created_at=now, updated_at=now, created_by=user["id"], updated_by=user["id"],
    )
    queued = False
    if body.auto_run:
        queued = await pipeline.queue_stage(db, stage_id, actor_id=user["id"])
    await db.commit()
    # 커밋 이후 conn 재획득 — 운영(Engine 바인딩)에서는 commit()이 raw 커넥션을 풀에
    # 반납하므로, 커밋 전에 얻은 conn을 그대로 쓰면 안 된다.
    conn = await raw_connection(db)
    if queued:
        # 큐 투입은 커밋 이후 — 워커가 아직 안 보이는 행을 집으면 안 된다.
        # queue_stage가 실패했다면(방금 insert한 행이라 실무상 없지만) enqueue도 하지
        # 않는다 — 워커가 claim_stage에서 조용히 버리는 것보다 의도를 명시하는 편이 낫다.
        get_worker().enqueue(stage_id)
    return await views.detail(conn, project_id)


@router.get("")
async def list_projects(user: dict = Depends(current_user), db: AsyncSession = Depends(get_db)):
    conn = await raw_connection(db)
    return [
        views.project_public(dict(r))
        async for r in queries.list_projects_by_owner(conn, owner_id=user["id"])
    ]


@router.get("/{project_id}")
async def get_project(
    project_id: int, user: dict = Depends(current_user), db: AsyncSession = Depends(get_db)
):
    conn = await raw_connection(db)
    await _load_owned_project(conn, project_id, user["id"])
    return await views.detail(conn, project_id)


@router.post("/{project_id}/stages/{name}/run", status_code=202)
async def run_stage(
    project_id: int, name: str, user: dict = Depends(current_user), db: AsyncSession = Depends(get_db)
):
    conn = await raw_connection(db)
    await _load_owned_project(conn, project_id, user["id"])
    stage = await _load_stage(conn, project_id, name)
    if not await pipeline.queue_stage(db, stage["id"], actor_id=user["id"]):
        # 코드는 기존과 같은 STAGE_CONFLICT를 유지한다(Errors.conflict는 CONFLICT라 다르다).
        raise AppError(409, "STAGE_CONFLICT", "이미 실행 중이거나 검토 단계입니다.")
    await db.commit()
    # 커밋 이후 conn 재획득 — 운영에서는 commit()이 raw 커넥션을 풀에 반납한다.
    conn = await raw_connection(db)
    # 큐 투입은 커밋 이후 — 워커가 아직 안 보이는 행을 집으면 안 된다.
    # 트레이드오프: enqueue를 views.detail보다 먼저 하므로, 운영에서는 워커가
    # views.detail의 DB 왕복 사이에 claim/commit을 끝내 202 본문이 QUEUED가 아니라
    # RUNNING/NEEDS_REVIEW로 보일 수 있다. 순서를 뒤집으면 views.detail 실패 시 enqueue가
    # 유실되는데(재기동 시 worker._recover()가 QUEUED를 다시 태우지만 그때까지 지연이 크다)
    # 그게 더 나쁘다고 판단해 이 순서를 유지한다.
    get_worker().enqueue(stage["id"])
    return await views.detail(conn, project_id)


@router.post("/{project_id}/stages/{name}/approve")
async def approve_stage(
    project_id: int, name: str, user: dict = Depends(current_user), db: AsyncSession = Depends(get_db)
):
    conn = await raw_connection(db)
    project = await _load_owned_project(conn, project_id, user["id"])
    stage = await _load_stage(conn, project_id, name)
    await pipeline.approve_stage(db, project, stage, actor_id=user["id"])  # 내부에서 commit
    # approve_stage가 이미 commit했다 — 커밋 이후 conn을 재획득해야 한다(운영에서는
    # commit()이 raw 커넥션을 풀에 반납한다).
    conn = await raw_connection(db)
    return await views.detail(conn, project_id)


@router.post("/{project_id}/stages/{name}/regenerate", status_code=202)
async def regenerate_stage(
    project_id: int, name: str, user: dict = Depends(current_user), db: AsyncSession = Depends(get_db)
):
    conn = await raw_connection(db)
    await _load_owned_project(conn, project_id, user["id"])
    stage = await _load_stage(conn, project_id, name)
    await pipeline.regenerate_stage(db, stage, actor_id=user["id"])  # 내부에서 commit
    # regenerate_stage가 이미 commit했다 — 커밋 이후 conn을 재획득해야 한다.
    conn = await raw_connection(db)
    get_worker().enqueue(stage["id"])
    return await views.detail(conn, project_id)


# 프록시 유휴 타임아웃을 막고 끊긴 클라이언트를 감지하는 간격.
_PING_INTERVAL_SEC = 15.0


def _sse(event: dict) -> str:
    return f"data: {json.dumps(event, ensure_ascii=False)}\n\n"


@router.get("/{project_id}/events")
async def project_events(
    project_id: int, user: dict = Depends(current_user), db: AsyncSession = Depends(get_db)
):
    conn = await raw_connection(db)
    await _load_owned_project(conn, project_id, user["id"])  # 남의 프로젝트면 404 — 스트림 밖에서, 진짜 404로

    async def stream():
        # 스냅샷을 읽기 전에 먼저 구독한다. 반대 순서(스냅샷 → 구독)로 하면 그 사이의
        # await db.close() / ASGI response.start 전송 같은 실제 suspension point에서
        # 워커가 발행한 이벤트가 아직 비어있는 구독자 집합으로 가 영영 유실된다 — 재생이
        # 없으므로 터미널 이벤트를 놓치면 화면이 RUNNING에 영원히 멈춘다. 대가로, 구독 직후
        # ~ 스냅샷 사이에 발행된 이벤트는 스냅샷보다 먼저 큐에 들어가 있다가 스냅샷 "다음"에
        # 전달될 수 있다(최신 스냅샷 뒤에 살짝 오래된 stage 이벤트가 오는 정도) — 자연히
        # 다음 이벤트로 덮어써지므로, 되돌리지 말 것.
        async with events.subscribe(project_id) as queue:
            snapshot = await views.detail(conn, project_id)
            # 접속 직후 현재 상태를 통째로 한 번 보낸다 → 프론트는 GET detail과 SSE의
            # 도착 순서를 신경 쓸 필요가 없다. 진행 중인 단계의 마지막 진행률도 함께 싣는다.
            snapshot["type"] = "snapshot"
            snapshot["progress"] = {
                stage["name"]: progress
                for stage in snapshot["stages"]
                if (progress := events.get_progress(stage["id"])) is not None
            }

            # SSE는 몇 시간씩 열려 있다. DB 작업은 여기서 끝났으므로 커넥션을 풀에 돌려준다
            # (안 그러면 접속자 수만큼 풀이 잠긴다). get_db의 정리는 중복 close라 무해하다.
            await db.close()

            yield _sse(snapshot)
            while True:
                try:
                    event = await asyncio.wait_for(queue.get(), timeout=_PING_INTERVAL_SEC)
                except TimeoutError:
                    yield ": ping\n\n"
                    continue
                yield _sse(event)

    return StreamingResponse(
        stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


# kind → 내려줄 MIME 타입. 새 산출물 종류가 생기면 여기 한 줄.
_MEDIA_TYPES = {
    AssetKind.AUDIO: "audio/mpeg",
    AssetKind.SRT: "application/x-subrip",
    AssetKind.VIDEO: "video/mp4",
}


@router.get("/{project_id}/stages/{name}/asset")
async def get_stage_asset(
    project_id: int, name: str, user: dict = Depends(current_user), db: AsyncSession = Depends(get_db)
):
    conn = await raw_connection(db)
    await _load_owned_project(conn, project_id, user["id"])  # 남의 프로젝트면 여기서 404
    stage = await _load_stage(conn, project_id, name)

    row = await queries.find_asset_by_stage(conn, stage_id=stage["id"])
    if row is None:
        raise Errors.not_found("산출물을 찾을 수 없습니다.")

    try:
        path = storage.resolve(row["path"])
    except ValueError:
        # 저장된 경로가 저장소 밖을 가리킨다(DB 오염 등). 500 대신 다른 실패와 같은 404로 답한다.
        raise Errors.not_found("산출물을 찾을 수 없습니다.")
    if not path.exists():
        # DB에는 있는데 파일이 없다 — 존재를 꾸며내지 않는다.
        raise Errors.not_found("산출물을 찾을 수 없습니다.")
    return FileResponse(path, media_type=_MEDIA_TYPES.get(row["kind"], "application/octet-stream"))
