import json

from fastapi import APIRouter, Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import require_admin
from app.constants import AuditAction, AuditTarget
from app.core import audit
from app.db import get_db, raw_connection
from app.queries import queries
from app.runtime_settings import (
    RuntimeSettings,
    get_runtime_settings,
    invalidate_runtime_settings,
)
from app.utils.time import now_local

router = APIRouter(prefix="/admin/system", tags=["admin"])


async def _snapshot(conn) -> dict:
    """화면이 필요로 하는 세 가지를 한 번에 준다.

    settings는 현재 유효값, defaults는 .env 기본값, overridden은 그 둘이 다른 키다
    (DB 행 존재 여부가 아니라 값 비교다 — delete-on-default 덕에 두 정의가 일치하지만,
    행이 남아도 값이 같으면 "변경됨"으로 보이지 않는 쪽이 더 견고하다).
    화면은 settings·defaults로 "변경됨" 배지와 [기본값으로] 링크를 직접 계산하고,
    overridden은 API 응답의 요약값으로만 쓴다.
    """
    current = await get_runtime_settings(conn)
    defaults = RuntimeSettings().model_dump()
    settings = current.model_dump()
    return {
        "settings": settings,
        "defaults": defaults,
        "overridden": sorted(k for k, v in settings.items() if v != defaults[k]),
    }


@router.get("/settings")
async def read_settings(
    db: AsyncSession = Depends(get_db),
    admin: dict = Depends(require_admin),
):
    return await _snapshot(await raw_connection(db))


@router.put("/settings")
async def write_settings(
    body: RuntimeSettings,
    request: Request,
    db: AsyncSession = Depends(get_db),
    admin: dict = Depends(require_admin),
):
    """전체 폼을 받아 저장한다.

    부분 업데이트를 받지 않는 이유는 "안 보낸 필드"와 "비운 필드"를 구분해야 해서
    화면과 서버가 같이 복잡해지기 때문이다. 공지 관리 모달과 같은 방식이다.
    """
    conn = await raw_connection(db)
    defaults = RuntimeSettings().model_dump()
    incoming = body.model_dump()
    now = now_local()

    # 변경 전 값은 get_runtime_settings가 아니라 DB에서 직접 읽는다 — 그 함수는 30초
    # TTL 캐시라, 방금 다른 프로세스가 바꾼 값을 "이전 값"으로 잘못 적을 수 있다.
    rows = [row async for row in queries.select_all_settings(conn)]
    before = RuntimeSettings.from_overrides({r["key"]: r["value"] for r in rows}).model_dump()

    for key, value in incoming.items():
        if value == defaults[key]:
            # 기본값으로 되돌린 항목은 행을 지운다 (없는 행 삭제는 그냥 0건이다).
            await queries.delete_setting(conn, key=key)
        else:
            await queries.upsert_setting(
                conn, key=key, value=json.dumps(value), now=now, actor_id=admin["id"]
            )

    # 화면이 폼 전체를 PUT하므로 실제로 바뀐 키만 골라야 기록이 의미를 갖는다.
    # 여기만 값을 남기는 이유: RuntimeSettings에는 민감값이 없고(API 키는 .env에만 있다),
    # "누가 비밀번호 최소 길이를 낮췄나"는 값 없이는 답할 수 없는 질문이다.
    changed = [k for k, v in incoming.items() if v != before[k]]
    if changed:
        await audit.record(
            conn,
            action=AuditAction.SYSTEM_SETTINGS_UPDATE,
            request=request,
            actor=admin,
            target_type=AuditTarget.SYSTEM,
            summary=", ".join(f"{k} {before[k]} → {incoming[k]}" for k in changed),
        )
    await db.commit()
    invalidate_runtime_settings()

    # 커밋이 raw 커넥션을 풀에 반납한다 — 재획득 후 읽는다.
    return await _snapshot(await raw_connection(db))
