import asyncio
import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

logger = logging.getLogger(__name__)

# 구독자 한 명이 밀리더라도 워커를 멈춰세우지 않도록 큐 길이를 묶는다.
_QUEUE_MAX = 100

_subscribers: dict[int, set[asyncio.Queue]] = {}
_last_progress: dict[int, dict] = {}


def publish(project_id: int, event: dict) -> None:
    """이 프로젝트를 보고 있는 구독자들에게 이벤트를 흘린다.

    절대 await하지 않고 예외도 밖으로 내보내지 않는다 — 이벤트 발행 실패가
    단계 실행을 죽이면 안 된다.
    """
    for queue in list(_subscribers.get(project_id, ())):
        try:
            queue.put_nowait(event)
        except asyncio.QueueFull:
            # 가장 오래된 것을 버리고 최신 이벤트를 넣는다. 진행률은 최신값만 의미가 있다.
            try:
                queue.get_nowait()
                queue.put_nowait(event)
            except (asyncio.QueueEmpty, asyncio.QueueFull):
                logger.warning("구독자 큐를 비우지 못했습니다: project=%s", project_id)
        except Exception:
            logger.exception("이벤트 발행 실패: project=%s", project_id)


@asynccontextmanager
async def subscribe(project_id: int) -> AsyncIterator[asyncio.Queue]:
    """이 프로젝트의 이벤트를 받을 큐를 등록한다. 블록을 벗어나면 반드시 해제된다."""
    queue: asyncio.Queue = asyncio.Queue(maxsize=_QUEUE_MAX)
    _subscribers.setdefault(project_id, set()).add(queue)
    try:
        yield queue
    finally:
        remaining = _subscribers.get(project_id)
        if remaining is not None:
            remaining.discard(queue)
            if not remaining:
                _subscribers.pop(project_id, None)


def set_progress(stage_id: int, payload: dict) -> None:
    """마지막 진행률을 기억한다. 뒤늦게 접속한 구독자의 스냅샷에 실린다(DB엔 남기지 않는다)."""
    _last_progress[stage_id] = payload


def get_progress(stage_id: int) -> dict | None:
    return _last_progress.get(stage_id)


def clear_progress(stage_id: int) -> None:
    _last_progress.pop(stage_id, None)


def reset() -> None:
    """테스트 전용 — 프로세스 전역 상태를 비운다."""
    _subscribers.clear()
    _last_progress.clear()
