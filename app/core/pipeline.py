import json

from app.constants import ProjectStatus, StageStatus
from app.db import raw_connection
from app.providers.base import StageContext, get_provider
from app.queries import queries
from app.utils.errors import AppError
from app.utils.time import now_local

STAGE_ORDER: list[str] = ["script"]  # voice/captions/render 미구현

# Stage.status 허용 전이. 여기 없는 전이는 모두 금지(잘못된 요청 → 409).
ALLOWED_TRANSITIONS: dict[str, set[str]] = {
    StageStatus.PENDING: {StageStatus.RUNNING},
    StageStatus.RUNNING: {StageStatus.NEEDS_REVIEW, StageStatus.FAILED},
    StageStatus.NEEDS_REVIEW: {StageStatus.APPROVED, StageStatus.PENDING},  # 승인 / 재생성
    StageStatus.FAILED: {StageStatus.PENDING},  # 재시도
    StageStatus.APPROVED: set(),  # 이 슬라이스의 종착
}


def can_transition(frm: str, to: str) -> bool:
    return to in ALLOWED_TRANSITIONS.get(frm, set())


def decode_stage(row: dict) -> dict:
    """asyncpg가 문자열로 돌려준 jsonb 컬럼(output/settings)을 dict로 되돌린 새 dict."""
    row = dict(row)
    for key in ("output", "settings"):
        value = row.get(key)
        if isinstance(value, str):
            row[key] = json.loads(value)
    return row


async def run_stage(session, project: dict, stage: dict, actor_id: int) -> dict:
    if stage["status"] not in (StageStatus.PENDING, StageStatus.FAILED):
        raise AppError(409, "STAGE_CONFLICT", "이미 실행 중이거나 검토 단계입니다.")

    conn = await raw_connection(session)
    started = now_local()
    provider = get_provider(stage["name"], stage["provider"])
    ctx = StageContext(
        topic=project["topic"],
        settings=project.get("settings", {}),
        inputs={},
        attempt=stage["attempt"],
    )
    try:
        result = await provider.run(ctx)
        status, output, error = StageStatus.NEEDS_REVIEW, result.output, None
    except Exception as exc:  # provider 예외는 삼키지 않고 상태로 기록
        status, output, error = StageStatus.FAILED, {}, str(exc)

    await queries.update_stage_run(
        conn, id=stage["id"], status=status, output=json.dumps(output), error=error,
        attempt=stage["attempt"], started_at=started, finished_at=now_local(),
        updated_at=now_local(), updated_by=actor_id,
    )
    await session.commit()
    updated = await queries.find_stage(conn, project_id=project["id"], name=stage["name"])
    return decode_stage(updated)


async def approve_stage(session, project: dict, stage: dict, actor_id: int) -> None:
    if not can_transition(stage["status"], StageStatus.APPROVED):
        raise AppError(409, "STAGE_CONFLICT", "승인할 수 없는 상태입니다.")

    conn = await raw_connection(session)
    now = now_local()
    await queries.update_stage_status(
        conn, id=stage["id"], status=StageStatus.APPROVED, updated_at=now, updated_by=actor_id
    )
    # script가 마지막 구현 단계라 프로젝트를 DONE으로 둔다.
    # 향후 여러 단계가 생기면 이 부분은 "다음 단계 PENDING 등록 + current_stage 갱신"으로 교체한다.
    await queries.update_project_status(
        conn, id=project["id"], status=ProjectStatus.DONE, current_stage=stage["name"],
        updated_at=now, updated_by=actor_id,
    )
    await session.commit()


async def regenerate_stage(session, project: dict, stage: dict, actor_id: int) -> dict:
    if not can_transition(stage["status"], StageStatus.PENDING):
        raise AppError(409, "STAGE_CONFLICT", "재생성할 수 없는 상태입니다.")

    conn = await raw_connection(session)
    now = now_local()
    new_attempt = stage["attempt"] + 1
    await queries.update_stage_run(
        conn, id=stage["id"], status=StageStatus.PENDING, output=json.dumps({}), error=None,
        attempt=new_attempt, started_at=None, finished_at=None, updated_at=now, updated_by=actor_id,
    )
    await session.commit()
    reloaded = decode_stage(await queries.find_stage(conn, project_id=project["id"], name=stage["name"]))
    return await run_stage(session, project, reloaded, actor_id=actor_id)
