from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from httpx import ASGITransport, AsyncClient

from app.main import mount_spa
from app.utils.errors import AppError


def _build_app(dist_dir) -> tuple[FastAPI, bool]:
    """정적 서빙만 얹은 최소 앱. /api 404가 JSON으로 나오는지 보려면
    실제 앱과 같은 AppError 핸들러가 필요하므로 여기서도 등록한다."""
    app = FastAPI()

    @app.exception_handler(AppError)
    async def _app_error(request: Request, exc: AppError) -> JSONResponse:
        return JSONResponse(status_code=exc.status_code, content={"code": exc.code, "message": exc.message})

    # /api/* 는 실제 라우터가 처리한다. 여기선 catch-all이 이 경로를 삼키지 않는지만
    # 보면 되므로, 존재하는 API 하나를 흉내 낸다.
    @app.get("/api/ping")
    async def _ping():
        return {"pong": True}

    mounted = mount_spa(app, dist_dir)
    return app, mounted


def _make_dist(tmp_path):
    dist = tmp_path / "dist"
    (dist / "assets").mkdir(parents=True)
    (dist / "index.html").write_text("<!doctype html><title>studio</title>", encoding="utf-8")
    (dist / "assets" / "app.js").write_text("console.log('app')", encoding="utf-8")
    (dist / "favicon.svg").write_text("<svg/>", encoding="utf-8")
    return dist


def test_mount_spa_returns_false_when_dist_missing(tmp_path):
    app, mounted = _build_app(tmp_path / "does-not-exist")
    assert mounted is False


def test_mount_spa_returns_false_when_index_missing(tmp_path):
    dist = tmp_path / "dist"
    (dist / "assets").mkdir(parents=True)  # index.html 없음
    app, mounted = _build_app(dist)
    assert mounted is False


async def test_serves_index_at_root(tmp_path):
    app, _ = _build_app(_make_dist(tmp_path))
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        resp = await c.get("/")
    assert resp.status_code == 200
    assert "studio" in resp.text
    assert resp.headers["content-type"].startswith("text/html")


async def test_spa_route_falls_back_to_index(tmp_path):
    """빌드에 없는 클라이언트 라우트(/projects/123)를 새로고침해도 index.html이 떠야 한다."""
    app, _ = _build_app(_make_dist(tmp_path))
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        resp = await c.get("/projects/123")
    assert resp.status_code == 200
    assert "studio" in resp.text


async def test_serves_hashed_asset(tmp_path):
    app, _ = _build_app(_make_dist(tmp_path))
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        resp = await c.get("/assets/app.js")
    assert resp.status_code == 200
    assert "console.log" in resp.text


async def test_serves_root_static_file(tmp_path):
    """favicon 같은 dist 루트 파일은 index.html이 아니라 그 파일 자체를 줘야 한다."""
    app, _ = _build_app(_make_dist(tmp_path))
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        resp = await c.get("/favicon.svg")
    assert resp.status_code == 200
    assert "<svg/>" in resp.text


async def test_api_route_is_not_shadowed(tmp_path):
    """catch-all이 등록돼도 실제 /api 라우트가 먼저 잡혀야 한다."""
    app, _ = _build_app(_make_dist(tmp_path))
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        resp = await c.get("/api/ping")
    assert resp.status_code == 200
    assert resp.json() == {"pong": True}


async def test_unknown_api_returns_json_404_not_index(tmp_path):
    """없는 API는 SPA index.html이 아니라 JSON 404여야 한다 — 프론트가 JSON을 기대하기 때문.
    폴백은 /api 경로를 건드리지 않으므로 FastAPI 기본 404({"detail": ...})가 그대로 나온다."""
    app, _ = _build_app(_make_dist(tmp_path))
    transport = ASGITransport(app=app, raise_app_exceptions=False)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        resp = await c.get("/api/nope")
    assert resp.status_code == 404
    assert resp.headers["content-type"].startswith("application/json")
    assert "studio" not in resp.text  # index.html이 아니어야 한다
    assert resp.json() == {"detail": "Not Found"}
