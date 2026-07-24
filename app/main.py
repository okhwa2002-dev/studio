import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.exception_handlers import http_exception_handler
from fastapi.responses import FileResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.api.health import router as health_router
from app.api.projects import router as projects_router
from app.auth.admin_router import router as admin_users_router
from app.auth.router import router as auth_router
from app.core.worker import get_worker
from app.utils.errors import DEFAULT_ERROR, AppError
from app.utils.logging import configure_logging

configure_logging()
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # 단계 실행은 요청이 아니라 이 워커가 맡는다. 기동 시 고아 상태도 여기서 정리된다.
    worker = get_worker()
    await worker.start()
    try:
        yield
    finally:
        await worker.stop()


app = FastAPI(title="Studio", lifespan=lifespan)
# 모든 API는 /api 아래에 둔다. 이렇게 하면 프론트 SPA 라우트(/admin/users 등)와
# 경로가 절대 겹치지 않아, 새로고침 시 문서 요청이 API로 새는 일이 없다
# (개발: Vite 프록시가 /api만 넘긴다 / 운영: FastAPI가 dist를 서빙해도 충돌 없음).
app.include_router(health_router, prefix="/api")
app.include_router(auth_router, prefix="/api")
app.include_router(admin_users_router, prefix="/api")
app.include_router(projects_router, prefix="/api")


@app.exception_handler(AppError)
async def app_error_handler(request: Request, exc: AppError) -> JSONResponse:
    return JSONResponse(
        status_code=exc.status_code,
        content={"code": exc.code, "message": exc.message},
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
