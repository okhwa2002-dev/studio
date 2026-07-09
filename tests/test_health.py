import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from app.db import get_db
from app.main import app
from app.models.error_code import ErrorCode
from app.utils.errors import AppError


@pytest_asyncio.fixture
async def client(db_session):
    async def _override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = _override_get_db
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c
    app.dependency_overrides.clear()


async def test_health_ok(client):
    resp = await client.get("/health")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}


async def test_app_error_uses_resolver(client, db_session):
    db_session.add(ErrorCode(code="DEFAULT", message="기본 오류", http_status=400, is_default=True, is_active=True))
    db_session.add(ErrorCode(code="BOOM", message="터짐", http_status=418, is_default=False, is_active=True))
    await db_session.commit()

    @app.get("/_boom")
    async def _boom():
        raise AppError("BOOM")

    resp = await client.get("/_boom")
    assert resp.status_code == 418
    assert resp.json() == {"code": "BOOM", "message": "터짐"}
