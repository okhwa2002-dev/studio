import json
import logging

from app.config import get_settings
from app.constants import ProjectStatus, StageStatus
from app.db import raw_connection
from app.providers.base import StageContext, get_provider
from app.queries import queries
from app.utils import storage
from app.utils.errors import AppError
from app.utils.time import now_local

logger = logging.getLogger(__name__)

STAGE_ORDER: list[str] = ["script", "voice", "captions", "render"]

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


def _decode_meta(value):
    """asyncpg가 문자열로 돌려준 assets.meta(jsonb)를 dict로 되돌린다."""
    return json.loads(value) if isinstance(value, str) else value


async def _previous_context(conn, project_id: int, upto: str) -> tuple[dict, dict]:
    """이 단계 앞 단계들의 (outputs, assets)를 한 번의 순회로 모은다.

    outputs: {단계이름: output}                       — 요약 JSON
    assets:  {단계이름: [{kind, path, meta}, ...]}    — 파일 산출물
    """
    outputs: dict = {}
    assets: dict = {}
    for name in STAGE_ORDER:
        if name == upto:
            break
        row = await queries.find_stage(conn, project_id=project_id, name=name)
        if row is None:
            continue
        outputs[name] = decode_stage(dict(row))["output"]
        assets[name] = [
            {"kind": r["kind"], "path": r["path"], "meta": _decode_meta(r["meta"])}
            async for r in queries.list_assets_by_stage(conn, stage_id=row["id"])
        ]
    return outputs, assets


async def _replace_assets(conn, stage_id: int, assets: list[dict], actor_id: int) -> None:
    """이 단계의 기존 산출물(행+파일)을 지우고 새 것으로 교체한다."""
    keep = {a["path"] for a in assets}
    for row in [dict(r) async for r in queries.list_assets_by_stage(conn, stage_id=stage_id)]:
        if row["path"] not in keep:  # 새로 덮어쓴 파일은 지우지 않는다
            storage.delete(row["path"])
    await queries.delete_assets_by_stage(conn, stage_id=stage_id)
    now = now_local()
    for asset in assets:
        await queries.insert_asset(
            conn, stage_id=stage_id, kind=asset["kind"], path=asset["path"],
            meta=json.dumps(asset.get("meta", {})),
            created_at=now, updated_at=now, created_by=actor_id, updated_by=actor_id,
        )


async def run_stage(session, project: dict, stage: dict, actor_id: int) -> dict:
    if stage["status"] not in (StageStatus.PENDING, StageStatus.FAILED):
        raise AppError(409, "STAGE_CONFLICT", "이미 실행 중이거나 검토 단계입니다.")

    conn = await raw_connection(session)
    started = now_local()
    claimed = await queries.claim_stage_run(
        conn, id=stage["id"], status=StageStatus.RUNNING,
        started_at=started, updated_at=started, updated_by=actor_id,
    )
    if claimed is None:
        # 다른 요청이 먼저 잡았거나 실행 가능한 상태가 아니다.
        raise AppError(409, "STAGE_CONFLICT", "이미 실행 중이거나 검토 단계입니다.")

    inputs, input_assets = await _previous_context(conn, project["id"], stage["name"])
    ctx = StageContext(
        topic=project["topic"],
        settings=project.get("settings", {}),
        inputs=inputs,
        input_assets=input_assets,
        attempt=stage["attempt"],
        workdir=f"projects/{project['id']}/{stage['name']}",
    )
    try:
        provider = get_provider(stage["name"], stage["provider"])   # 잘못된 provider 이름도 FAILED로 흡수
        provider.validate(ctx.settings)          # 키 누락 등 조기 실패 → FAILED로 흡수
        result = await provider.run(ctx)
        await _replace_assets(conn, stage["id"], result.assets, actor_id)
        status, output, error = StageStatus.NEEDS_REVIEW, result.output, None
    except AppError as exc:  # validate 실패·PROVIDER_NOT_FOUND 등 친절 메시지 그대로
        status, output, error = StageStatus.FAILED, {}, exc.message
    except Exception:  # 외부 SDK 오류(429/5xx/파싱 등)는 원문 대신 일반 안내 + 로그
        logger.exception("stage run failed: project=%s stage=%s", project["id"], stage["name"])
        status, output, error = StageStatus.FAILED, {}, "실행 중 오류가 발생했습니다. 잠시 후 다시 시도해 주세요."

    await queries.update_stage_run(
        conn, id=stage["id"], status=status, output=json.dumps(output), error=error,
        attempt=stage["attempt"], started_at=started, finished_at=now_local(),
        updated_at=now_local(), updated_by=actor_id,
    )
    await session.commit()
    updated = await queries.find_stage(conn, project_id=project["id"], name=stage["name"])
    return decode_stage(updated)


def _next_stage(name: str) -> str | None:
    """STAGE_ORDER에서 다음 단계 이름. 마지막이면 None."""
    idx = STAGE_ORDER.index(name)
    return STAGE_ORDER[idx + 1] if idx + 1 < len(STAGE_ORDER) else None


def _next_provider(name: str) -> str:
    """단계별 기본 provider는 설정에서 온다. 설정이 없으면 fake."""
    return getattr(get_settings(), f"{name}_provider", "fake")


async def approve_stage(session, project: dict, stage: dict, actor_id: int) -> None:
    if not can_transition(stage["status"], StageStatus.APPROVED):
        raise AppError(409, "STAGE_CONFLICT", "승인할 수 없는 상태입니다.")

    conn = await raw_connection(session)
    now = now_local()
    await queries.update_stage_status(
        conn, id=stage["id"], status=StageStatus.APPROVED, updated_at=now, updated_by=actor_id
    )

    nxt = _next_stage(stage["name"])
    if nxt is None:
        # 마지막 구현 단계를 승인하면 프로젝트 완료.
        await queries.update_project_status(
            conn, id=project["id"], status=ProjectStatus.DONE, current_stage=stage["name"],
            updated_at=now, updated_by=actor_id,
        )
    else:
        # 다음 단계를 PENDING으로 등록만 한다 — 실행은 사용자가 [실행]으로 시작한다.
        # 이미 있으면 만들지 않는다(재승인 멱등). 단, APPROVED가 종착 상태(ALLOWED_TRANSITIONS[APPROVED] = set())라
        # 재승인 자체가 API로는 이 지점에 도달하지 못한다 — 방어적 검사로, 훗날 APPROVED 재진입을 허용할 때를 대비해 남겨둔다.
        if await queries.find_stage(conn, project_id=project["id"], name=nxt) is None:
            await queries.insert_stage(
                conn, project_id=project["id"], name=nxt, provider=_next_provider(nxt),
                status=StageStatus.PENDING, output=json.dumps({}), error=None, attempt=0,
                started_at=None, finished_at=None,
                created_at=now, updated_at=now, created_by=actor_id, updated_by=actor_id,
            )
        await queries.update_project_status(
            conn, id=project["id"], status=ProjectStatus.REVIEW, current_stage=nxt,
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
