from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from app.api.health import router as health_router
from app.db import get_db
from app.utils.errors import AppError, resolve_error

app = FastAPI(title="Studio")
app.include_router(health_router)


@app.exception_handler(AppError)
async def app_error_handler(request: Request, exc: AppError) -> JSONResponse:
    provider = app.dependency_overrides.get(get_db, get_db)
    agen = provider()
    session = await agen.__anext__()
    try:
        resolved = await resolve_error(session, exc.code, exc.message)
    finally:
        await agen.aclose()
    return JSONResponse(
        status_code=resolved.http_status,
        content={"code": resolved.code, "message": resolved.message},
    )
