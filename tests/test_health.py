import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from app.main import app
from app.utils.errors import AppError


@pytest_asyncio.fixture
async def client():
    # raise_app_exceptions=False: 핸들러가 처리한 500 응답도 그대로 받아서
    # 검증할 수 있도록 한다(기본값 True면 예외가 테스트 쪽으로 다시 던져짐).
    transport = ASGITransport(app=app, raise_app_exceptions=False)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


async def test_health_ok(client):
    resp = await client.get("/health")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}


async def test_app_error_returns_its_own_code_and_message(client):
    @app.get("/_boom")
    async def _boom():
        raise AppError(418, "BOOM", "터짐")

    resp = await client.get("/_boom")
    assert resp.status_code == 418
    assert resp.json() == {"code": "BOOM", "message": "터짐"}


async def test_unhandled_exception_falls_back_to_default_error(client):
    @app.get("/_unexpected")
    async def _unexpected():
        raise RuntimeError("something truly unexpected")

    resp = await client.get("/_unexpected")
    assert resp.status_code == 500
    assert resp.json() == {"code": "UNKNOWN_ERROR", "message": "알 수 없는 오류가 발생했습니다."}
