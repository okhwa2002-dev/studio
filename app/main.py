import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.exception_handlers import http_exception_handler
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.api.admin_audit_logs import router as admin_audit_logs_router
from app.api.admin_faqs import router as admin_faqs_router
from app.api.admin_notices import router as admin_notices_router
from app.api.admin_projects import router as admin_projects_router
from app.api.admin_system import router as admin_system_router
from app.api.dashboard import router as dashboard_router
from app.api.faqs import router as faqs_router
from app.api.health import router as health_router
from app.api.notices import router as notices_router
from app.api.projects import router as projects_router
from app.auth.admin_router import router as admin_users_router
from app.auth.router import router as auth_router
from app.config import get_settings
from app.core.cleanup import get_cleanup_job
from app.core.worker import get_worker
from app.runtime_settings import EnvSettingsError, check_env_defaults
from app.utils.errors import DEFAULT_ERROR, AppError
from app.utils.logging import configure_logging

configure_logging()
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # 런타임 설정의 기본값은 .env에서 온다. 범위를 벗어난 .env는 여기서 기동을 멈춘다 —
    # 그러지 않으면 "관리자가 손대지도 않은 항목 때문에 시스템 설정이 저장되지 않는"
    # 식으로 한참 뒤 엉뚱한 곳에서 드러난다. 트레이스백만으로는 어떤 키가 문제인지
    # 알 수 없으므로, 고쳐야 할 키와 이유를 먼저 로그로 남기고 예외를 그대로 올린다.
    try:
        check_env_defaults()
    except EnvSettingsError as exc:
        logger.error("%s", exc)
        raise

    # 운영에서 SMTP_HOST를 빠뜨리면 메일이 조용히 파일로 간다. 기동을 막지는 않는다 —
    # 개발 환경에서는 그것이 정상 경로다. 대신 그 상태를 기동 로그에 드러낸다.
    if not get_settings().smtp_host:
        logger.warning(
            "SMTP_HOST가 없어 메일을 보내지 않고 파일로 저장합니다: %s/mail",
            get_settings().log_dir,
        )

    # 단계 실행은 요청이 아니라 이 워커가 맡는다. 기동 시 고아 상태도 여기서 정리된다.
    worker = get_worker()
    await worker.start()
    # 수명주기가 끝난 데이터(만료 토큰·보관 기간 지난 삭제 프로젝트)를 주기적으로 지운다.
    cleanup_job = get_cleanup_job()
    await cleanup_job.start()
    try:
        yield
    finally:
        await cleanup_job.stop()
        await worker.stop()


app = FastAPI(title="Studio", lifespan=lifespan)
# 모든 API는 /api 아래에 둔다. 이렇게 하면 프론트 SPA 라우트(/admin/users 등)와
# 경로가 절대 겹치지 않아, 새로고침 시 문서 요청이 API로 새는 일이 없다
# (개발: Vite 프록시가 /api만 넘긴다 / 운영: FastAPI가 dist를 서빙해도 충돌 없음).
app.include_router(health_router, prefix="/api")
app.include_router(auth_router, prefix="/api")
app.include_router(admin_users_router, prefix="/api")
app.include_router(admin_audit_logs_router, prefix="/api")
app.include_router(admin_notices_router, prefix="/api")
app.include_router(admin_faqs_router, prefix="/api")
app.include_router(admin_projects_router, prefix="/api")
app.include_router(admin_system_router, prefix="/api")
app.include_router(dashboard_router, prefix="/api")
app.include_router(faqs_router, prefix="/api")
app.include_router(notices_router, prefix="/api")
app.include_router(projects_router, prefix="/api")


@app.exception_handler(AppError)
async def app_error_handler(request: Request, exc: AppError) -> JSONResponse:
    return JSONResponse(
        status_code=exc.status_code,
        content={"code": exc.code, "message": exc.message},
    )


# loc의 앞머리는 값이 어디서 왔는지(body/query/...)를 가리킬 뿐 항목 이름이 아니다.
_LOC_PREFIXES = ("body", "query", "path", "header", "cookie")


@app.exception_handler(RequestValidationError)
async def validation_error_handler(
    request: Request, exc: RequestValidationError
) -> JSONResponse:
    """FastAPI 기본 422 본문({"detail": [...]})을 프로젝트 공통 {code, message}로 바꾼다.

    프론트의 toApiError는 code·message만 읽는다. 그래서 기본 본문 그대로 두면 화면에
    "알 수 없는 오류가 발생했습니다." 한 줄만 뜨고 어떤 항목이 왜 거부됐는지 알 수 없다.
    특히 시스템 설정 화면은 14개 필드를 한 번에 PUT하므로 항목 이름이 없으면 손쓸 수가 없다.
    상태 코드는 422 그대로 둔다 — 기존 테스트·클라이언트의 기대를 바꾸지 않는다.
    """
    message = "요청 값이 올바르지 않습니다."
    errors = exc.errors()
    if errors:
        first = errors[0]
        field = ".".join(
            str(part) for part in first.get("loc", ()) if part not in _LOC_PREFIXES
        )
        # 커스텀 validator가 낸 메시지에는 pydantic이 "Value error, " 접두사를 붙인다.
        reason = str(first.get("msg", "")).removeprefix("Value error, ")
        message = f"{field}: {reason}" if field else reason or message
    return JSONResponse(
        status_code=422,
        content={"code": "VALIDATION_ERROR", "message": message},
    )


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    # AppError가 아닌, 정말 예상 못한 예외. 원본 예외 내용을 응답에 노출하지
    # 않고 소스에 고정된 디폴트 에러로 응답한다. 실제 원인은 로그로 남긴다.
    logger.exception("Unhandled exception on %s %s", request.method, request.url.path)
    return JSONResponse(
        status_code=DEFAULT_ERROR.status_code,
        content={"code": DEFAULT_ERROR.code, "message": DEFAULT_ERROR.message},
    )


# 운영에서 프론트(web/dist)를 API와 같은 출처로 서빙한다. 동일 출처여야 httpOnly +
# SameSite=Lax 인증 쿠키가 성립한다(README "동일 출처 규칙"). 개발에선 dist가 없고
# Vite가 대신 프록시하므로, mount_spa는 아무것도 하지 않는다.
_DIST_DIR = Path(__file__).resolve().parent.parent / "web" / "dist"


def mount_spa(app: FastAPI, dist_dir: Path) -> bool:
    """web/dist가 있으면 SPA를 서빙한다. 없으면(빌드 전/개발) 아무것도 하지 않고 False.

    catch-all 라우트가 아니라 404 폴백으로 구현한다 — 그래야 (뒤늦게 등록된 것을 포함해)
    실제 라우트가 항상 먼저 매칭되고, 정말 매칭되지 않은 경로만 index.html로 넘어간다.
    /api의 404는 지금과 똑같이 유지된다.
    """
    dist_dir = dist_dir.resolve()
    index = dist_dir / "index.html"
    if not index.is_file():
        return False

    # Vite가 낸 해시 붙은 번들. 대부분의 정적 요청이 이 마운트로 직접 처리된다.
    assets = dist_dir / "assets"
    if assets.is_dir():
        app.mount("/assets", StaticFiles(directory=assets), name="assets")

    @app.exception_handler(StarletteHTTPException)
    async def spa_fallback(request: Request, exc: StarletteHTTPException) -> Response:
        # 매칭 실패(404) + 문서 요청(GET/HEAD) + /api 밖 → 클라이언트 라우트로 보고 SPA를 준다.
        # /api의 404, 405 등 나머지는 FastAPI 기본 처리에 그대로 넘긴다(응답 형태 유지).
        if (
            exc.status_code == 404
            and request.method in ("GET", "HEAD")
            and not request.url.path.startswith("/api")
        ):
            # dist 안의 실제 파일(favicon 등)이면 그 파일을, 아니면 SPA 진입점을 준다.
            # resolve로 정규화한 뒤 dist 안에 있는지 확인해 경로 탈출(../)을 막는다.
            candidate = (dist_dir / request.url.path.lstrip("/")).resolve()
            if candidate != dist_dir and dist_dir in candidate.parents and candidate.is_file():
                return FileResponse(candidate)
            return FileResponse(index)
        return await http_exception_handler(request, exc)

    return True


mount_spa(app, _DIST_DIR)
