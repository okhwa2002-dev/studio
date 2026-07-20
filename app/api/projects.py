import json

from fastapi import APIRouter, Depends
from fastapi.responses import FileResponse
from pydantic import BaseModel, field_validator
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import current_user
from app.config import get_settings
from app.constants import AssetKind, ProjectStatus, StageName, StageStatus
from app.core import pipeline
from app.db import get_db, raw_connection
from app.queries import queries
from app.utils import storage
from app.utils.errors import Errors
from app.utils.time import now_local

router = APIRouter(prefix="/projects", tags=["projects"])


def _project_public(project: dict) -> dict:
    return {
        "id": project["id"],
        "title": project["title"],
        "topic": project["topic"],
        "status": project["status"],
        "current_stage": project["current_stage"],
        "created_at": project["created_at"].isoformat() if project.get("created_at") else None,
    }


def _stage_public(stage: dict) -> dict:
    return {
        "id": stage["id"],
        "name": stage["name"],
        "provider": stage["provider"],
        "status": stage["status"],
        "output": stage["output"],
        "error": stage["error"],
        "attempt": stage["attempt"],
    }


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


async def _detail(conn, project_id: int) -> dict:
    project = pipeline.decode_stage(await queries.find_project_by_id(conn, id=project_id))
    stages = [
        _stage_public(pipeline.decode_stage(dict(r)))
        async for r in queries.list_stages_by_project(conn, project_id=project_id)
    ]
    return {"project": _project_public(project), "stages": stages}


class CreateProjectRequest(BaseModel):
    title: str
    topic: str

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
        status=ProjectStatus.DRAFT, current_stage=StageName.SCRIPT, settings=json.dumps({}),
        created_at=now, updated_at=now, created_by=user["id"], updated_by=user["id"],
    )
    await queries.insert_stage(
        conn, project_id=project_id, name=StageName.SCRIPT, provider=get_settings().script_provider,
        status=StageStatus.PENDING, output=json.dumps({}), error=None, attempt=0,
        started_at=None, finished_at=None,
        created_at=now, updated_at=now, created_by=user["id"], updated_by=user["id"],
    )
    await db.commit()
    return await _detail(conn, project_id)


@router.get("")
async def list_projects(user: dict = Depends(current_user), db: AsyncSession = Depends(get_db)):
    conn = await raw_connection(db)
    return [
        _project_public(dict(r))
        async for r in queries.list_projects_by_owner(conn, owner_id=user["id"])
    ]


@router.get("/{project_id}")
async def get_project(
    project_id: int, user: dict = Depends(current_user), db: AsyncSession = Depends(get_db)
):
    conn = await raw_connection(db)
    await _load_owned_project(conn, project_id, user["id"])
    return await _detail(conn, project_id)


@router.post("/{project_id}/stages/{name}/run")
async def run_stage(
    project_id: int, name: str, user: dict = Depends(current_user), db: AsyncSession = Depends(get_db)
):
    conn = await raw_connection(db)
    project = await _load_owned_project(conn, project_id, user["id"])
    stage = await _load_stage(conn, project_id, name)
    await pipeline.run_stage(db, project, stage, actor_id=user["id"])
    return await _detail(conn, project_id)


@router.post("/{project_id}/stages/{name}/approve")
async def approve_stage(
    project_id: int, name: str, user: dict = Depends(current_user), db: AsyncSession = Depends(get_db)
):
    conn = await raw_connection(db)
    project = await _load_owned_project(conn, project_id, user["id"])
    stage = await _load_stage(conn, project_id, name)
    await pipeline.approve_stage(db, project, stage, actor_id=user["id"])
    return await _detail(conn, project_id)


@router.post("/{project_id}/stages/{name}/regenerate")
async def regenerate_stage(
    project_id: int, name: str, user: dict = Depends(current_user), db: AsyncSession = Depends(get_db)
):
    conn = await raw_connection(db)
    project = await _load_owned_project(conn, project_id, user["id"])
    stage = await _load_stage(conn, project_id, name)
    await pipeline.regenerate_stage(db, project, stage, actor_id=user["id"])
    return await _detail(conn, project_id)


# kind → 내려줄 MIME 타입. 새 산출물 종류가 생기면 여기 한 줄.
_MEDIA_TYPES = {AssetKind.AUDIO: "audio/mpeg"}


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
