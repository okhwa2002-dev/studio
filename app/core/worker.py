import asyncio
import logging

from app.config import get_settings
from app.constants import STAGE_LABEL, AuditAction, AuditTarget, StageStatus
from app.core import audit, events, pipeline, views
from app.db import async_session_maker, raw_connection
from app.queries import queries
from app.utils.errors import AppError
from app.utils.time import now_local

logger = logging.getLogger(__name__)

# 종료 시 진행 중인 단계를 이만큼 기다린 뒤 취소한다.
_SHUTDOWN_GRACE_SEC = 5.0
_RESTART_ERROR = "서버가 재시작되어 중단되었습니다. 다시 실행해 주세요."


class StageWorker:
    """stages 테이블을 큐로 삼아 단계를 백그라운드에서 실행한다.

    session_factory를 주입받는 이유: 워커가 async_session_maker를 직접 잡으면
    테스트의 SAVEPOINT 격리 밖으로 나가 테스트 데이터를 못 보고 실제 DB에 쓴다.
    """

    def __init__(self, session_factory=None, concurrency: int | None = None):
        self._session_factory = session_factory or async_session_maker
        self._concurrency = concurrency or get_settings().worker_concurrency
        self._queue: asyncio.Queue[int] = asyncio.Queue()
        self._tasks: list[asyncio.Task] = []

    def enqueue(self, stage_id: int) -> None:
        """실행 대기열에 넣는다. 상태 선점(QUEUED)은 호출자가 이미 끝냈다고 본다."""
        self._queue.put_nowait(stage_id)

    async def start(self) -> None:
        await self._recover()
        self._tasks = [
            asyncio.create_task(self._loop(), name=f"stage-worker-{i}")
            for i in range(self._concurrency)
        ]

    async def stop(self) -> None:
        if not self._tasks:
            return
        try:
            await asyncio.wait_for(self._queue.join(), timeout=_SHUTDOWN_GRACE_SEC)
        except TimeoutError:
            logger.warning("%.0f초 안에 끝나지 않은 단계가 있어 취소합니다.", _SHUTDOWN_GRACE_SEC)
        for task in self._tasks:
            task.cancel()
        await asyncio.gather(*self._tasks, return_exceptions=True)
        self._tasks = []

    async def _loop(self) -> None:
        while True:
            stage_id = await self._queue.get()
            try:
                await self.run_one(stage_id)
            except Exception:
                # 한 단계의 실패가 워커 루프를 죽이면 안 된다.
                logger.exception("단계 실행 중 처리되지 않은 예외: stage=%s", stage_id)
            finally:
                self._queue.task_done()

    async def _recover(self) -> None:
        """앱이 죽으면서 남은 고아 상태를 정리한다. 기동 시 1회."""
        async with self._session_factory() as session:
            conn = await raw_connection(session)
            now = now_local()
            # RUNNING은 중간 산출물 상태를 알 수 없다 — 되살리지 않고 실패로 확정한다.
            # 프로세스 하나가 이 테이블의 RUNNING을 전부 소유한다고 가정한다 — 인스턴스를
            # 여러 개 띄우면 다른 인스턴스가 실제로 돌리는 중인 단계까지 실패 처리된다.
            await queries.fail_running_stages(
                conn, error=_RESTART_ERROR, finished_at=now, updated_at=now
            )
            # QUEUED는 아직 시작 전이므로 그대로 다시 태운다.
            queued = [r["id"] async for r in queries.list_queued_stage_ids(conn)]
            await session.commit()
        for stage_id in queued:
            self.enqueue(stage_id)
        if queued:
            logger.info("기동 복구: 대기 중이던 단계 %d건을 다시 큐에 넣었습니다.", len(queued))

    async def run_one(self, stage_id: int) -> None:
        """한 단계를 선점해 실행하고 결과를 이벤트로 알린다."""
        async with self._session_factory() as session:
            conn = await raw_connection(session)
            row = await queries.find_stage_by_id(conn, id=stage_id)
            if row is None:
                return
            project_row = await queries.find_project_by_id(conn, id=row["project_id"])
            if project_row is None:
                return  # 중간에 프로젝트가 지워졌다 — decode_stage(None)로 죽지 않고 조용히 버린다
            project = pipeline.decode_stage(project_row)
            actor = project["owner_id"]

            stage = await pipeline.claim_stage(session, stage_id, actor_id=actor)
            if stage is None:
                return  # 경합에서 졌거나 QUEUED가 아니다 — 조용히 버린다
            await session.commit()  # 발행은 항상 커밋 이후
            events.publish(project["id"], views.stage_event(project, stage))

            try:
                on_progress = self._make_on_progress(project["id"], stage["id"], stage["name"])
                updated = await pipeline.run_claimed_stage(
                    session, project, stage, actor_id=actor, on_progress=on_progress
                )
                # commit 이후 세션이 쥐고 있던 raw 커넥션은 갈렸을 수 있다 — 프로덕션에서는
                # commit()이 풀에 커넥션을 반납하고 세션이 다음에 새로 체크아웃한다. 방금
                # run_claimed_stage가 내부에서 또 commit했으므로, 여기서부터는 다시 얻어야 한다.
                conn = await raw_connection(session)
                project_row = await queries.find_project_by_id(conn, id=project["id"])
                if project_row is None:
                    return  # 실행 도중 프로젝트가 지워졌다 — decode_stage(None)로 죽지 않고 조용히 버린다
                project = pipeline.decode_stage(project_row)
                events.publish(project["id"], views.stage_event(project, updated))
                try:
                    await self._chain_if_auto(session, project, updated, actor)
                except Exception:
                    # _chain_if_auto의 실패를 run_one 실패와 구분해서 기록한다 — 안 그러면
                    # 이미 성공·커밋된 이 단계가 _loop의 핸들러에 "실행 실패"로 오기록된다.
                    logger.exception("자동 진행 연쇄 실패: stage=%s", stage_id)
            finally:
                # RUNNING 커밋 이후 여기서 예외(DB 오류)나 취소(stop()의 유예 이후
                # CancelledError)가 나도 진행률 잔재만은 반드시 지운다 — 안 지우면 죽은
                # 단계의 진행률 바가 나중 구독자에게 그대로 보인다.
                events.clear_progress(stage["id"])
                # 여기서 종료 상태(FAILED 등)를 억지로 써넣지 않는다. RUNNING으로 남는 것은
                # 의도된 트레이드오프이며, 정리는 기동 시 _recover()가 전담한다. run_claimed_stage
                # 등의 예외는 삼키지 않고 그대로 _loop의 핸들러로 전파한다(_chain_if_auto의
                # 예외는 위에서 이미 자체 로그로 구분해 처리했으므로 여기까지 오지 않는다).

    async def _chain_if_auto(self, session, project: dict, stage: dict, actor: int) -> None:
        """자동 진행 모드면 검토를 건너뛰고 다음 단계까지 밀어준다.

        승인은 기존 approve_stage 경로를 그대로 태운다 — 자동/수동이 같은 코드를
        지나므로 상태 머신에 새 규칙이 필요 없다. 실패하면 여기 오지 않고 멈춘다.

        감사 기록도 같은 이유로 수동 승인과 같은 STAGE_APPROVE를 남긴다. 여기를 빼면
        auto_run 프로젝트는 4단계를 다 지나 DONE이 되어도 STAGE_APPROVE가 한 건도
        남지 않아, 관리자에게 "아무도 승인하지 않았는데 완료된 프로젝트"로 보인다.
        """
        if stage["status"] != StageStatus.NEEDS_REVIEW:
            return
        if not project.get("settings", {}).get("auto_run"):
            return

        conn = await raw_connection(session)
        # 행위자 스냅샷(email·name)을 채우려면 사용자 행이 필요하다. 자동 승인은 단계당
        # 한 번뿐이라 추가 조회 한 번이 아깝지 않다. 행이 없으면(도달 불가 — 사용자는
        # 하드 삭제되지 않는다) 스냅샷 없이 남긴다. 기록 자체를 빼는 것보다 낫다.
        actor_row = await queries.find_by_id(conn, id=actor)
        # 기록을 approve_stage 앞에 두는 이유는 app/api/projects.py의 approve_stage와 같다:
        # approve_stage가 내부에서 commit하므로 이 행이 그 커밋에 함께 실린다. 뒤에 두면
        # 커밋되지 않은 채 남아 세션이 닫힐 때 조용히 사라진다. 승인이 STAGE_CONFLICT로
        # 끝나면(사용자 조작이 먼저 이겼다) 이 행도 함께 롤백되는데, 그게 맞는 동작이다.
        await audit.record(
            conn,
            action=AuditAction.STAGE_APPROVE,
            request=None,  # 요청 밖에서 일어나는 사건 — http_*·actor_ip는 NULL이다(설계 2-4)
            actor=dict(actor_row) if actor_row is not None else None,
            target_type=AuditTarget.PROJECT,
            target_id=project["id"],
            target_label=project["title"],
            summary=f"{STAGE_LABEL.get(stage['name'], stage['name'])} 단계 자동 승인",
        )

        try:
            await pipeline.approve_stage(session, project, stage, actor_id=actor)
        except AppError as exc:
            if exc.code != "STAGE_CONFLICT":
                raise
            # approve_stage의 CAS가 0행을 반환했다 — 그 사이 사용자가 재생성 등으로
            # 상태를 먼저 바꿨다는 뜻이다. 사용자의 명시적 조작이 자동 진행보다 우선해야
            # 하므로 에러가 아니라 정상적인 자동 진행 중단으로 보고 조용히 멈춘다.
            logger.info("자동 진행 연쇄 중단(사용자 조작이 우선함): stage=%s", stage["id"])
            return
        # approve_stage가 내부에서 이미 commit했다 — run_one과 같은 이유로 conn을
        # 재획득해야 한다(프로덕션에서 commit은 커넥션을 풀에 반납한다).
        conn = await raw_connection(session)
        approved = pipeline.decode_stage(await queries.find_stage_by_id(conn, id=stage["id"]))
        project = pipeline.decode_stage(await queries.find_project_by_id(conn, id=project["id"]))
        events.publish(project["id"], views.stage_event(project, approved))

        nxt = pipeline.next_stage(stage["name"])
        if nxt is None:
            return  # 마지막 단계 — approve_stage가 프로젝트를 DONE으로 만들었다
        nxt_row = await queries.find_stage(conn, project_id=project["id"], name=nxt)
        if nxt_row is None:
            return
        if not await pipeline.queue_stage(session, nxt_row["id"], actor_id=actor):
            return
        await session.commit()
        # 다시 커밋했다 — 다음 조회 전에 또 재획득한다.
        conn = await raw_connection(session)
        queued = pipeline.decode_stage(await queries.find_stage_by_id(conn, id=nxt_row["id"]))
        events.publish(project["id"], views.stage_event(project, queued))
        # 재귀 호출이 아니라 큐를 경유한다 — 4단계를 돌아도 스택이 자라지 않는다.
        self.enqueue(nxt_row["id"])

    def _make_on_progress(self, project_id: int, stage_id: int, stage_name: str):
        """진행률 콜백을 만든다.

        whisper·ffmpeg는 asyncio.to_thread 안에서 돌므로 콜백이 워커 스레드에서
        불린다. 이벤트 버스는 이벤트 루프 것이므로 루프로 넘겨서 만진다.
        """
        loop = asyncio.get_running_loop()

        def _apply(payload: dict) -> None:
            events.set_progress(stage_id, payload)
            events.publish(project_id, payload)

        def on_progress(percent: float | None, message: str) -> None:
            loop.call_soon_threadsafe(_apply, views.progress_event(stage_name, percent, message))

        return on_progress


_worker: StageWorker | None = None


def get_worker() -> StageWorker:
    """앱 전역 워커. lifespan이 start/stop을 부르고 API가 enqueue한다."""
    global _worker
    if _worker is None:
        _worker = StageWorker()
    return _worker


def reset() -> None:
    """테스트 전용 — 전역 워커 싱글턴을 비운다. 다음 get_worker() 호출이 새로 만든다."""
    global _worker
    _worker = None
