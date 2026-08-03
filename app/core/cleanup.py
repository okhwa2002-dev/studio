import asyncio
import logging
from datetime import timedelta

from app.constants import AuditAction, AuditTarget
from app.core import audit
from app.core.error_log import SOURCE_CLEANUP, record_error
from app.db import async_session_maker, raw_connection
from app.queries import queries
from app.utils import storage
from app.utils.time import now_local

logger = logging.getLogger(__name__)

# 24시간마다. 기동 직후에도 한 번 돈다 — 개발·배포 중 앱이 자주 재시작되는데
# 매번 24시간을 기다리면 잡이 사실상 돌지 않는다.
PURGE_INTERVAL_SEC = 24 * 60 * 60

# 소프트 삭제된 프로젝트를 완전히 지우기까지 남겨두는 기간.
# 소스 상수로 두는 이유: .env로 빼면 기동 시 범위 검증(check_env_defaults)까지 붙어야 하고,
# 관리자가 이 값을 바꿀 이유가 아직 없다. 필요해지면 runtime_settings로 올린다.
PROJECT_RETENTION_DAYS = 30

# 감사 로그 보관 기간. PROJECT_RETENTION_DAYS와 같은 이유로 소스 상수다 —
# .env로 빼면 기동 시 범위 검증(check_env_defaults)까지 붙어야 하고, 관리자가
# 이 값을 바꿀 이유가 아직 없다. 필요해지면 runtime_settings로 올린다.
AUDIT_RETENTION_DAYS = 90

# 에러 로그 보관 기간. 감사 로그(90일)보다 짧은 이유는 성격이 달라서다 — 감사 로그는
# "누가 무엇을 했는가"의 기록이라 나중에 되짚을 일이 있지만, 에러는 고쳐지면 그만이고
# 30일이면 주기적 장애도 한 번은 잡힌다.
ERROR_RETENTION_DAYS = 30


async def _purge_expired_tokens(session) -> None:
    """만료된 refresh token을 지운다.

    조건이 expires_at < now 하나여야 하는 이유가 중요하다. auth/router.py의 refresh는
    **이미 폐기된 토큰이 다시 제시되면 탈취로 보고 그 사용자의 모든 세션을 끊는다.**
    이 경보는 폐기된 행이 DB에 남아 있어야 동작한다 — revoked_at IS NOT NULL을 삭제
    조건에 넣으면 탈취된 토큰의 재사용이 "없는 토큰"으로 보여 평범한 401이 나가고
    경보가 영구히 죽는다.

    만료 후에는 지워도 안전하다. 만료된 토큰으로는 새 세션을 받을 수 없으므로 공격자가
    얻을 것이 없다. 즉 이 정리는 테이블을 비우는 것이 아니라 상한을 씌우는 것이다
    (정상 크기 = 활성 사용자 수 × 토큰 유효기간).
    """
    conn = await raw_connection(session)
    await queries.delete_expired_refresh_tokens(conn, now=now_local())
    await session.commit()


async def _purge_expired_reset_codes(session) -> None:
    """만료된 비밀번호 재설정 코드를 지운다.

    refresh 토큰과 달리 소비된 행을 보존할 이유가 없다. 그쪽은 폐기 토큰의 재사용을
    탈취로 잡는 경보가 행의 존재에 의존하지만, 재설정 코드에는 대응하는 경보가 없다 —
    소비됐든 지워졌든 _resolve_reset_code는 똑같은 INVALID_RESET_CODE를 던진다.

    시도 한도(5회)도 무력화되지 않는다. 삭제는 만료 후에만 일어나 살아 있는 코드의
    attempts는 건드리지 않고, 공격자가 새로 요청해봐야 새 난수 코드를 받을 뿐이다.

    건수를 로그로 남기지 않는 것은 _purge_expired_tokens와 같은 이유다 — 10분마다
    갈리는 부산물이라 건수에 운영 신호가 없다.
    """
    conn = await raw_connection(session)
    await queries.delete_expired_reset_codes(conn, now=now_local())
    await session.commit()


async def _purge_project(session, project_id: int, title: str | None) -> None:
    """프로젝트 하나를 행·파일까지 완전히 지운다.

    순서가 이 함수의 핵심이다. 행을 먼저 지우고 파일을 지운 뒤 **마지막에 커밋**한다.

    커밋을 먼저 하면 중간 실패 시 "행은 없는데 파일만 남는" 조합이 생기고, 그 파일은
    어느 화면에서도 닿을 수 없으며 찾아낼 잡도 없어 영구 고아가 된다. 커밋을 마지막에
    두면 그 조합이 구조적으로 불가능하다 — 실패하면 파일이 일부 지워진 채 행이 살아
    있는데, 그 행은 이미 소프트 삭제 상태라 사용자에게 보이지 않고 다음 주기가 마무리한다.

    FK에 ON DELETE CASCADE가 없어서 자식부터 직접 지운다(assets → stages → projects).
    """
    conn = await raw_connection(session)
    await queries.delete_assets_by_project(conn, project_id=project_id)
    await queries.delete_stages_by_project(conn, project_id=project_id)
    await queries.delete_project(conn, id=project_id)
    # 감사 기록은 행 삭제 직후, 파일 삭제·커밋보다 앞에 둔다. record는 커밋하지 않고
    # 현재 트랜잭션에 INSERT만 하므로 마지막 commit()에 함께 실린다 — 위 순서 규칙을
    # 깨지 않는다. 파일 삭제 뒤로 미루면 delete_tree가 던졌을 때 기록만 남고 실제로는
    # 정리가 끝나지 않은 상태가 되는데, 그 조합은 이 함수가 피하려는 바로 그 것이다.
    # target_label(제목)은 위에서 행을 지웠으므로 더 이상 읽을 수 없다 —
    # list_purgeable_projects가 id와 함께 미리 읽어 넘겨준다.
    await audit.record(
        conn,
        action=AuditAction.PROJECT_PURGE,
        request=None,  # 요청 밖에서 도는 잡이다 — http_*·actor_ip는 NULL(설계 2-4)
        actor=None,    # 사람이 한 일이 아니다
        target_type=AuditTarget.PROJECT,
        target_id=project_id,
        target_label=title,
        summary="보관 기간 경과로 완전 삭제",
    )
    # workdir이 pipeline에서 projects/{id}/{stage}로만 정해지므로 이 서브트리가 그
    # 프로젝트의 파일 전부다 — asset으로 기록되지 않는 스톡 소재까지 함께 사라진다.
    storage.delete_tree(f"projects/{project_id}")
    await session.commit()


def _affected(status) -> int:
    """asyncpg가 돌려준 명령 상태 문자열("DELETE 5")에서 건수를 뽑는다.

    aiosql의 asyncpg 어댑터가 `!` 쿼리의 결과로 이 문자열을 그대로 돌려준다
    (정수 추출은 아직 구현돼 있지 않다). 모양이 다르면 0으로 본다 — 로그 한 줄 때문에
    정리 잡이 죽으면 안 된다.
    """
    parts = str(status).split()
    return int(parts[-1]) if parts and parts[-1].isdigit() else 0


async def _purge_old_audit_logs(session) -> None:
    """보관 기간이 지난 활동 기록을 지운다.

    감사 로그는 append-only라 지우는 경로가 여기 하나뿐이다. 멱등한 DELETE이므로
    같은 잡이 두 번 돌아도, 인스턴스가 둘이어도 문제가 없다.

    이 삭제 자체는 감사 기록을 남기지 않는다 — 감사 로그를 지운 사실을 감사 로그에
    남기면 자기참조로 매 주기 한 건씩 무한히 늘어난다. 대신 건수를 서버 로그로 남긴다.
    """
    conn = await raw_connection(session)
    before = now_local() - timedelta(days=AUDIT_RETENTION_DAYS)
    status = await queries.delete_old_audit_logs(conn, before=before)
    await session.commit()
    deleted = _affected(status)
    if deleted:
        logger.info("보관 기간이 지난 활동 기록 %d건을 삭제했습니다.", deleted)


async def _purge_old_error_logs(session) -> None:
    """보관 기간이 지난 에러 로그를 지운다.

    기준이 updated_at(마지막 발생)인 것이 핵심이다. created_at으로 지우면 오래전에
    처음 났지만 지금도 나고 있는 에러가 사라진다 — 가장 오래 방치된, 그래서 가장 봐야 할
    항목이 먼저 지워지는 셈이다.

    건수를 로그로 남기는 것은 _purge_old_audit_logs와 같은 이유다. 이 테이블은 지문
    단위라 행 수가 적어, 지워진 건수에 "얼마나 다양한 에러가 있었나"는 운영 신호가 있다.
    """
    conn = await raw_connection(session)
    before = now_local() - timedelta(days=ERROR_RETENTION_DAYS)
    status = await queries.delete_old_error_logs(conn, before=before)
    await session.commit()
    deleted = _affected(status)
    if deleted:
        logger.info("보관 기간이 지난 에러 로그 %d건을 삭제했습니다.", deleted)


async def run_once(session_factory=None) -> None:
    """정리를 한 번 수행한다.

    주기 루프와 분리된 공개 함수인 이유: 24시간을 기다리는 테스트는 쓸 수 없으므로
    테스트가 이 함수를 직접 부른다. 루프는 이것을 주기적으로 부르는 껍데기다.
    """
    factory = session_factory or async_session_maker

    async with factory() as session:
        await _purge_expired_tokens(session)

    async with factory() as session:
        await _purge_expired_reset_codes(session)

    async with factory() as session:
        await _purge_old_audit_logs(session)

    async with factory() as session:
        await _purge_old_error_logs(session)

    async with factory() as session:
        conn = await raw_connection(session)
        before = now_local() - timedelta(days=PROJECT_RETENTION_DAYS)
        # 제목까지 함께 읽는다 — 행을 지운 뒤에는 감사 기록의 target_label을 채울 수 없다.
        targets = [
            (r["id"], r["title"])
            async for r in queries.list_purgeable_projects(conn, before=before)
        ]

    # 프로젝트는 한 건씩 각자의 트랜잭션으로 지운다 — 한 건이 실패해도 나머지가 함께
    # 롤백되지 않고, 실패한 건은 다음 주기가 다시 집는다.
    purged = 0
    for project_id, title in targets:
        try:
            async with factory() as session:
                await _purge_project(session, project_id, title)
            purged += 1
        except Exception as exc:
            logger.exception("프로젝트 완전 삭제 실패: project=%s", project_id)
            await record_error(SOURCE_CLEANUP, exc, context=f"project={project_id}")

    if purged:
        logger.info("보관 기간이 지난 프로젝트 %d건을 완전히 삭제했습니다.", purged)


class CleanupJob:
    """수명주기가 끝난 데이터를 주기적으로 지운다.

    session_factory를 주입받는 이유는 StageWorker와 같다: 잡이 async_session_maker를
    직접 잡으면 테스트의 SAVEPOINT 격리 밖으로 나가 실제 DB에 쓴다.

    동시 인스턴스는 문제가 아니다 — 모든 작업이 멱등한 DELETE라 두 인스턴스가 같은
    프로젝트를 지워도 한쪽이 0행을 지울 뿐이다. 워커의 단일 인스턴스 전제보다 느슨하다.
    """

    def __init__(self, session_factory=None):
        self._session_factory = session_factory
        self._task: asyncio.Task | None = None

    async def start(self) -> None:
        self._task = asyncio.create_task(self._loop(), name="cleanup-job")

    async def stop(self) -> None:
        if self._task is None:
            return
        self._task.cancel()
        await asyncio.gather(self._task, return_exceptions=True)
        self._task = None

    async def _loop(self) -> None:
        while True:
            try:
                await run_once(self._session_factory)
            except Exception as exc:
                # 정리 실패가 앱을 죽이거나 다음 주기를 멈추면 안 된다(워커 _loop과 같은 방침).
                logger.exception("정리 잡 실행 중 처리되지 않은 예외")
                await record_error(SOURCE_CLEANUP, exc)
            await asyncio.sleep(PURGE_INTERVAL_SEC)


_job: CleanupJob | None = None


def get_cleanup_job() -> CleanupJob:
    """앱 전역 정리 잡. lifespan이 start/stop을 부른다."""
    global _job
    if _job is None:
        _job = CleanupJob()
    return _job


def reset() -> None:
    """테스트 전용 — 전역 싱글턴을 비운다. 다음 get_cleanup_job()이 새로 만든다."""
    global _job
    _job = None
