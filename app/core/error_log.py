import asyncio
import logging
import traceback
from pathlib import Path

from app.db import async_session_maker, raw_connection
from app.queries import queries
from app.utils.time import now_local

logger = logging.getLogger(__name__)

# 발생 계층. app/constants.py의 enum으로 올리지 않는 이유는 이 값이 화면에 노출되지
# 않아 라벨 매핑 규칙(AUDIT_ACTION_LABEL 대응)을 따를 대상이 아니기 때문이다.
# 관리자 화면이 생기면 그때 올린다.
SOURCE_HTTP = "http"
SOURCE_WORKER = "worker"
SOURCE_PIPELINE = "pipeline"
SOURCE_CLEANUP = "cleanup"
SOURCE_EMAIL = "email"

_MESSAGE_MAX = 200
_CONTEXT_MAX = 200
_FINGERPRINT_MAX = 255

# DB가 죽으면 모든 요청이 500이 나는데, 그때 기록 시도가 커넥션 타임아웃(수 초)만큼
# 매달리면 500 응답까지 함께 느려진다 — 에러를 기록하려다 장애를 키우는 셈이다.
RECORD_TIMEOUT_SEC = 2.0

# 테스트가 SAVEPOINT 격리 안에서 검증할 수 있도록 교체 가능하게 둔다.
# worker·cleanup이 session_factory를 주입받는 것과 같은 이유다 — 기본값을 직접
# 잡으면 테스트가 개발자의 실제 DB에 쓴다.
_session_factory = None

# 앱 패키지 루트(.../app). 트레이스백에서 우리 코드 프레임을 고를 때 기준으로 쓴다.
# 경로 파트에 "app"이 있는지로 판별하면 Docker의 관용적인 WORKDIR /app 배포에서
# /app/.venv/lib/... 안의 라이브러리 프레임까지 전부 앱 코드로 잡혀, location이
# SDK 내부를 가리키는 쓸모없는 값이 된다.
_APP_ROOT = Path(__file__).resolve().parent.parent


def set_session_factory(factory) -> None:
    """테스트 전용 — 기록이 쓸 세션 팩토리를 갈아끼운다."""
    global _session_factory
    _session_factory = factory


def reset() -> None:
    """테스트 전용 — 전역을 비운다. 다음 호출이 app 기본 팩토리를 쓴다."""
    global _session_factory
    _session_factory = None


def _clip(value: str, limit: int) -> str:
    return value[:limit]


def _is_app_frame(filename: str) -> bool:
    """이 프레임이 app 패키지 안의 우리 코드인가.

    <string>·frozen 프레임처럼 실제 경로가 아닌 값도 들어오므로 넓게 잡아 삼킨다 —
    위치를 못 고르는 것이 기록 자체를 실패시키면 안 된다.
    """
    try:
        Path(filename).resolve().relative_to(_APP_ROOT)
    except Exception:
        return False
    return True


def _location(exc: BaseException) -> str:
    """트레이스백에서 앱 코드의 '디렉토리/파일:줄'만 뽑는다.

    스택트레이스 전문을 저장하지 않는 이유는 거기에 값이 섞일 수 있기 때문이다.
    가장 안쪽의 **앱 코드** 프레임을 고르는 이유는, 라이브러리 내부 줄을 가리켜 봐야
    고칠 지점을 알려주지 못하기 때문이다.
    """
    frames = traceback.extract_tb(exc.__traceback__)
    if not frames:
        return "unknown"
    app_frames = [f for f in frames if _is_app_frame(f.filename)]
    frame = app_frames[-1] if app_frames else frames[-1]
    path = Path(frame.filename)
    return f"{path.parent.name}/{path.name}:{frame.lineno}"


async def _write(source: str, exc_type: str, location: str, message: str, context: str | None):
    factory = _session_factory or async_session_maker
    fingerprint = _clip(f"{source}:{exc_type}@{location}", _FINGERPRINT_MAX)
    now = now_local()
    async with factory() as session:
        conn = await raw_connection(session)
        await queries.upsert_error_log(
            conn,
            fingerprint=fingerprint,
            source=source,
            exc_type=exc_type,
            location=location,
            message=message,
            context=context,
            now=now,
        )
        await session.commit()


async def record_error(source: str, exc: BaseException, context: str | None = None) -> None:
    """에러를 error_logs에 지문 단위로 집계한다.

    **예외(Exception)를 밖으로 내보내지 않는다.** 에러를 기록하다 실패해서 원래
    응답이 더 망가지면 본말전도다. 다만 취소(CancelledError)는 그대로 전파한다 —
    BaseException이라 아래 except에 걸리지 않고, 걸리게 만들면 종료 신호를 삼켜
    worker.stop()·cleanup_job.stop()이 끝나지 않는다.

    2초 상한도 best-effort다. wait_for는 만료 시 태스크를 취소한 뒤 되감기가 끝나기를
    기다리므로, 병목이 커넥션 획득이 아니라 세션 정리에 있으면 조금 넘길 수 있다.

    자기 세션을 연다. 백그라운드 태스크·워커·정리 잡에서 불리는데, FastAPI 0.106부터
    yield 의존성의 정리 코드가 백그라운드 태스크보다 먼저 돌아 요청 세션은 이미 닫혀
    있다. 500 핸들러에서도 요청 세션은 방금 터진 예외로 트랜잭션이 깨져 있을 수 있다.

    호출자 규칙: context에 비밀(인증코드·비밀번호·토큰)을 넣지 않는다. 이 함수는
    요청 본문·헤더·쿠키를 스스로 긁지 않으므로, 담기는 값은 호출자가 넘긴 것뿐이다.
    """
    try:
        await asyncio.wait_for(
            _write(
                source=source,
                exc_type=type(exc).__name__,
                location=_location(exc),
                message=_clip(str(exc), _MESSAGE_MAX),
                context=_clip(context, _CONTEXT_MAX) if context is not None else None,
            ),
            timeout=RECORD_TIMEOUT_SEC,
        )
    except Exception:
        # 여기서 스택을 남기지 않는다 — DB 장애 때 이 경고가 초당 수백 줄 찍히면
        # 정작 원인이 된 로그가 묻힌다. 원래 예외는 호출부가 이미 logger.exception으로
        # 남겼다.
        logger.warning("에러 로그 기록 실패: source=%s", source)
