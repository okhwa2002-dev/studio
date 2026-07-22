import asyncio

from app.core import events

PROJECT_ID = 7


async def test_publish_reaches_every_subscriber():
    async with events.subscribe(PROJECT_ID) as a, events.subscribe(PROJECT_ID) as b:
        events.publish(PROJECT_ID, {"type": "stage"})
        assert a.get_nowait() == {"type": "stage"}
        assert b.get_nowait() == {"type": "stage"}


async def test_publish_ignores_other_projects():
    async with events.subscribe(PROJECT_ID) as queue:
        events.publish(PROJECT_ID + 1, {"type": "stage"})
        assert queue.empty()


async def test_unsubscribe_on_exit():
    async with events.subscribe(PROJECT_ID):
        pass
    # 구독자가 사라지면 발행이 아무 데도 쌓이지 않는다(누수 없음).
    events.publish(PROJECT_ID, {"type": "stage"})
    assert events._subscribers == {}


async def test_full_queue_drops_oldest_and_keeps_newest():
    # 느린 구독자 하나가 워커를 멈춰세우면 안 된다. 진행률은 최신값만 의미가 있다.
    async with events.subscribe(PROJECT_ID) as queue:
        for i in range(events._QUEUE_MAX + 5):
            events.publish(PROJECT_ID, {"type": "progress", "n": i})
        drained = []
        while not queue.empty():
            drained.append(queue.get_nowait())
    assert len(drained) == events._QUEUE_MAX
    assert drained[-1] == {"type": "progress", "n": events._QUEUE_MAX + 4}


async def test_progress_cache_roundtrip():
    assert events.get_progress(11) is None
    events.set_progress(11, {"percent": 40.0, "message": "받아쓰는 중…"})
    assert events.get_progress(11)["percent"] == 40.0
    events.clear_progress(11)
    assert events.get_progress(11) is None


async def test_publish_never_raises():
    # 발행 실패가 파이프라인을 죽이면 안 된다.
    class Exploding(asyncio.Queue):
        def put_nowait(self, item):
            raise RuntimeError("boom")

    events._subscribers.setdefault(PROJECT_ID, set()).add(Exploding())
    events.publish(PROJECT_ID, {"type": "stage"})  # 예외가 새어 나오면 실패
