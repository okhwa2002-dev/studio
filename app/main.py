import logging

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from app.api.health import router as health_router
from app.auth.admin_router import router as admin_users_router
from app.auth.router import router as auth_router
from app.utils.errors import DEFAULT_ERROR, AppError
from app.utils.logging import configure_logging

configure_logging()
logger = logging.getLogger(__name__)

app = FastAPI(title="Studio")
# 모든 API는 /api 아래에 둔다. 이렇게 하면 프론트 SPA 라우트(/admin/users 등)와
# 경로가 절대 겹치지 않아, 새로고침 시 문서 요청이 API로 새는 일이 없다
# (개발: Vite 프록시가 /api만 넘긴다 / 운영: FastAPI가 dist를 서빙해도 충돌 없음).
app.include_router(health_router, prefix="/api")
app.include_router(auth_router, prefix="/api")
app.include_router(admin_users_router, prefix="/api")


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
