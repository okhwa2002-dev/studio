import httpx
import pytest

from app.utils import storage
from app.utils.stock.base import StockTooLarge
from app.utils.stock.download import download


def _transport(response_factory):
    return httpx.MockTransport(lambda request: response_factory(request))


@pytest.mark.asyncio
async def test_download_writes_file_and_returns_size(monkeypatch, tmp_path):
    monkeypatch.setattr(storage, "_root", lambda: tmp_path)
    transport = _transport(lambda r: httpx.Response(200, content=b"x" * 500))

    written = await download("https://cdn/clip.mp4", "projects/5/render/sources/scene1.mp4",
                             max_bytes=1000, timeout_sec=5, transport=transport)

    assert written == 500
    assert (tmp_path / "projects/5/render/sources/scene1.mp4").read_bytes() == b"x" * 500


@pytest.mark.asyncio
async def test_download_creates_parent_directories(monkeypatch, tmp_path):
    monkeypatch.setattr(storage, "_root", lambda: tmp_path)
    transport = _transport(lambda r: httpx.Response(200, content=b"ok"))

    await download("https://cdn/c.mp4", "projects/6/render/sources/scene1.mp4",
                   max_bytes=1000, timeout_sec=5, transport=transport)

    assert (tmp_path / "projects/6/render/sources/scene1.mp4").exists()


@pytest.mark.asyncio
async def test_download_over_limit_raises_and_removes_partial_file(monkeypatch, tmp_path):
    # 반쪽짜리 파일을 ffmpeg에 물리면 원인 찾기 어려운 실패가 난다 — 반드시 지운다
    monkeypatch.setattr(storage, "_root", lambda: tmp_path)
    transport = _transport(lambda r: httpx.Response(200, content=b"x" * 5000))

    with pytest.raises(StockTooLarge):
        await download("https://cdn/huge.mp4", "projects/7/render/sources/scene1.mp4",
                       max_bytes=100, timeout_sec=5, transport=transport)

    assert not (tmp_path / "projects/7/render/sources/scene1.mp4").exists()


@pytest.mark.asyncio
async def test_download_http_error_raises_and_removes_partial_file(monkeypatch, tmp_path):
    monkeypatch.setattr(storage, "_root", lambda: tmp_path)
    transport = _transport(lambda r: httpx.Response(404))

    with pytest.raises(httpx.HTTPStatusError):
        await download("https://cdn/gone.mp4", "projects/8/render/sources/scene1.mp4",
                       max_bytes=1000, timeout_sec=5, transport=transport)

    assert not (tmp_path / "projects/8/render/sources/scene1.mp4").exists()


@pytest.mark.asyncio
async def test_download_rejects_path_outside_storage(monkeypatch, tmp_path):
    monkeypatch.setattr(storage, "_root", lambda: tmp_path)
    transport = _transport(lambda r: httpx.Response(200, content=b"x"))

    with pytest.raises(ValueError):
        await download("https://cdn/c.mp4", "../escape.mp4",
                       max_bytes=1000, timeout_sec=5, transport=transport)
