"""API 응답과 SSE 이벤트가 함께 쓰는 공개 표현(shape).

api에 두면 워커가 쓸 수 없고 core→api 역방향 의존이 생긴다. core에 둔다.
"""

from app.core.pipeline import decode_stage
from app.queries import queries


def project_public(project: dict) -> dict:
    return {
        "id": project["id"],
        "title": project["title"],
        "topic": project["topic"],
        "status": project["status"],
        "current_stage": project["current_stage"],
        "created_at": project["created_at"].isoformat() if project.get("created_at") else None,
    }


def stage_public(stage: dict) -> dict:
    return {
        "id": stage["id"],
        "name": stage["name"],
        "provider": stage["provider"],
        "status": stage["status"],
        "output": stage["output"],
        "error": stage["error"],
        "attempt": stage["attempt"],
    }


async def detail(conn, project_id: int) -> dict:
    project = decode_stage(await queries.find_project_by_id(conn, id=project_id))
    stages = [
        stage_public(decode_stage(dict(r)))
        async for r in queries.list_stages_by_project(conn, project_id=project_id)
    ]
    return {"project": project_public(project), "stages": stages}


def stage_event(project: dict, stage: dict) -> dict:
    """단계 상태가 바뀌었다. 프로젝트 status/current_stage도 함께 실어 한 번에 갱신시킨다."""
    return {
        "type": "stage",
        "project": project_public(project),
        "stage": stage_public(stage),
    }


def progress_event(stage_name: str, percent: float | None, message: str) -> dict:
    """percent가 None이면 진짜 진행률이 없다는 뜻 — UI는 불확정 바를 보여준다."""
    return {
        "type": "progress",
        "stage": stage_name,
        "percent": percent,
        "message": message,
    }
