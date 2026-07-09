import logging

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from app.api.health import router as health_router
from app.db import get_db
from app.utils.errors import AppError, HARDCODED_FALLBACK, resolve_error
from app.utils.logging import configure_logging

configure_logging()
logger = logging.getLogger(__name__)

app = FastAPI(title="Studio")
app.include_router(health_router)


@app.exception_handler(AppError)
async def app_error_handler(request: Request, exc: AppError) -> JSONResponse:
    try:
        provider = app.dependency_overrides.get(get_db, get_db)
        agen = provider()
        try:
            session = await agen.__anext__()
            resolved = await resolve_error(session, exc.code, exc.message)
        finally:
            await agen.aclose()
    except Exception:
        # DB 자체가 응답하지 않는 경우에도 에러 응답 형식({"code","message"})은
        # 반드시 지켜야 하므로, 조회 경로의 어떤 예외든 하드코딩 폴백으로 대체한다.
        logger.exception("Failed to resolve error code=%s via DB; using hardcoded fallback", exc.code)
        resolved = HARDCODED_FALLBACK

    return JSONResponse(
        status_code=resolved.http_status,
        content={"code": resolved.code, "message": resolved.message},
    )
