import asyncio
import json

from fastapi import APIRouter, Depends
from fastapi.responses import FileResponse, StreamingResponse
from pydantic import BaseModel, Field, field_validator
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import current_user
from app.constants import AssetKind, ProjectStatus, StageName, StageStatus, UserRole
from app.core import events, pipeline, views
from app.core.worker import get_worker
from app.db import get_db, raw_connection
from app.providers.script.schema import build_draft
from app.queries import queries
from app.runtime_settings import get_runtime_settings
from app.utils import storage
from app.utils.errors import AppError, Errors
from app.utils.time import now_local

router = APIRouter(prefix="/projects", tags=["projects"])


async def _load_owned_project(conn, project_id: int, user_id: int) -> dict:
    row = await queries.find_project_by_id(conn, id=project_id)
    if row is None or row["owner_id"] != user_id:
        raise Errors.not_found("프로젝트를 찾을 수 없습니다.")
    return pipeline.decode_stage(row)  # settings jsonb 디코드


async def _load_project_for_read(conn, project_id: int, user: dict) -> dict:
    # 읽기 전용 경로(상세 SSE·에셋)는 소유자뿐 아니라 관리자도 허용한다.
    # 쓰기(실행·승인·재생성)는 여전히 _load_owned_project로 소유자만 통과시킨다.
    row = await queries.find_project_by_id(conn, id=project_id)
    if row is None or (row["owner_id"] != user["id"] and user["role"] != UserRole.ADMIN):
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
    runtime = await get_runtime_settings(conn)
    stage_id = await queries.insert_stage(
        conn, project_id=project_id, name=StageName.SCRIPT, provider=runtime.script_provider,
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


# 편집 상한. 60초 쇼츠에 한참 넉넉하게 두고, TTS·렌더가 몇십 분짜리를 물지 않게만 막는다.
_MAX_SCENES = 20
_MAX_NARRATION_CHARS = 2000        # 장면당
_MAX_TOTAL_NARRATION_CHARS = 5000  # 전체 합 (초당 5자로 약 17분)


class SceneEdit(BaseModel):
    narration: str = Field(max_length=_MAX_NARRATION_CHARS)
    # on_screen은 비어도 된다 — 스톡 검색이 topic으로 폴백한다(render/sources.queries_for).
    on_screen: str = Field(default="", max_length=200)

    @field_validator("narration")
    @classmethod
    def _narration_not_blank(cls, v: str) -> str:
        # 나레이션이 곧 음성이다. 비면 무음 mp3가 만들어진다.
        v = v.strip()
        if not v:
            raise ValueError("나레이션은 비워둘 수 없습니다.")
        return v


class ScriptEditRequest(BaseModel):
    """사람이 편집한 대본. 사용자가 실제로 통제하는 필드만 받는다.

    index와 estimated_duration_sec는 서버가 유도하므로(build_draft) 받지 않는다.
    기존 ScriptDraft를 그대로 쓰지 않는 이유가 이것이다 — 그 모델은 둘 다 필수다.
    또 상한을 ScriptDraft에 넣으면 AI 생성 경로까지 그 규칙에 걸려(장면 25개를 낸 응답이
    FAILED가 된다) 이 기능과 무관한 동작이 바뀐다.
    """

    title: str = Field(max_length=200)
    hook: str = Field(default="", max_length=500)  # 표시 전용이라 비어도 깨지지 않는다
    scenes: list[SceneEdit] = Field(min_length=1, max_length=_MAX_SCENES)

    @field_validator("title")
    @classmethod
    def _title_not_blank(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("제목은 비워둘 수 없습니다.")
        return v

    @field_validator("scenes")
    @classmethod
    def _total_narration_within_limit(cls, v: list[SceneEdit]) -> list[SceneEdit]:
        total = sum(len(scene.narration) for scene in v)
        if total > _MAX_TOTAL_NARRATION_CHARS:
            raise ValueError(
                f"나레이션 전체 길이가 {_MAX_TOTAL_NARRATION_CHARS}자를 넘습니다 (현재 {total}자)."
            )
        return v


@router.put("/{project_id}/stages/script")
async def save_script(
    project_id: int,
    body: ScriptEditRequest,
    user: dict = Depends(current_user),
    db: AsyncSession = Depends(get_db),
):
    """검토 중인 대본을 사람이 고친 내용으로 교체한다.

    편집할 수 있는 단계는 대본뿐이라 경로에 script를 리터럴로 박는다 — /stages/{name}으로
    열어두면 음성·자막·영상도 편집 가능한 것처럼 읽힌다.
    """
    conn = await raw_connection(db)
    await _load_owned_project(conn, project_id, user["id"])
    stage = await _load_stage(conn, project_id, StageName.SCRIPT)

    draft = build_draft(
        body.title, body.hook, [(s.narration, s.on_screen) for s in body.scenes]
    )
    # 상태 검사는 DB의 CAS에 맡긴다 — 여기서 읽은 stage["status"]는 이미 낡았을 수 있다.
    saved = await queries.update_stage_output_cas(
        conn,
        id=stage["id"],
        output=json.dumps(draft.model_dump(), ensure_ascii=False),
        expected_status=StageStatus.NEEDS_REVIEW,
        updated_at=now_local(),
        updated_by=user["id"],
    )
    if saved is None:
        raise AppError(409, "STAGE_CONFLICT", "수정할 수 없는 상태입니다.")
    await db.commit()
    # 커밋 이후 conn 재획득 — 운영에서는 commit()이 raw 커넥션을 풀에 반납한다.
    conn = await raw_connection(db)
    return await views.detail(conn, project_id)


@router.delete("/{project_id}")
async def delete_project(
    project_id: int, user: dict = Depends(current_user), db: AsyncSession = Depends(get_db)
):
    """프로젝트를 소프트 삭제한다. 파일은 그대로 두고 정리 잡이 보관 기간 후에 지운다.

    소유자만 지울 수 있다 — 관리자는 열람 전용이고(admin 화면은 readOnly) 실행·승인·재생성도
    모두 소유자 전용이라, 삭제만 예외로 두면 그 경계가 무너진다.
    """
    conn = await raw_connection(db)
    await _load_owned_project(conn, project_id, user["id"])

    # 워커가 손대는 중이면 막는다. 사용자가 몇 분 걸리는 작업 중에 삭제를 누르는 것은 대개
    # 실수이고, QUEUED인 채로 지우면 워커가 run_one 맨 앞에서 프로젝트를 못 찾아 조용히
    # 버리므로 그 단계가 영구히 QUEUED로 남는다.
    active = await queries.count_active_stages(conn, project_id=project_id)
    if active["n"] > 0:
        raise AppError(
            409, "PROJECT_BUSY", "실행 중인 단계가 있어 삭제할 수 없습니다. 완료된 뒤 다시 시도해 주세요."
        )

    now = now_local()
    await queries.soft_delete_project(conn, id=project_id, deleted_at=now, deleted_by=user["id"])
    await db.commit()
    return {"id": project_id, "deleted_at": now}


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
    await _load_project_for_read(conn, project_id, user)  # 소유자·관리자만. 아니면 404 — 스트림 밖에서, 진짜 404로

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
    await _load_project_for_read(conn, project_id, user)  # 소유자·관리자면 통과, 아니면 404
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
