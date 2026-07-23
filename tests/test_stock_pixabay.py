import httpx
import pytest

from app.config import get_settings
from app.utils.stock.base import PHOTO, VIDEO
from app.utils.stock.pixabay import PixabaySource

_VIDEO_RESPONSE = {
    "hits": [
        {
            "id": 333,
            "pageURL": "https://pixabay.com/videos/rain-333/",
            "duration": 18,
            "user": "이영희",
            "videos": {
                "large": {"url": "https://cdn/large.mp4", "width": 1920, "height": 1080},
                "medium": {"url": "https://cdn/medium.mp4", "width": 1280, "height": 720},
                "tiny": {"url": "https://cdn/tiny.mp4", "width": 640, "height": 360},
            },
        }
    ]
}

_PHOTO_RESPONSE = {
    "hits": [
        {
            "id": 444,
            "pageURL": "https://pixabay.com/photos/road-444/",
            "user": "박민수",
            "largeImageURL": "https://cdn/large.jpg",
            "imageWidth": 3000,
            "imageHeight": 4500,
        }
    ]
}


@pytest.fixture(autouse=True)
def _fresh_settings():
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


def _stub(payload, spy=None):
    async def _get_json(url, params, headers):
        if spy is not None:
            spy.append({"url": url, "params": params, "headers": headers})
        return payload

    return _get_json


@pytest.mark.asyncio
async def test_video_search_maps_to_clip(monkeypatch):
    monkeypatch.setenv("PIXABAY_API_KEY", "k")
    clips = await PixabaySource(get_json=_stub(_VIDEO_RESPONSE)).search("빗소리", VIDEO)

    assert len(clips) == 1
    clip = clips[0]
    assert clip.source == "pixabay"
    assert clip.kind == VIDEO
    assert clip.id == "333"
    assert clip.url == "https://cdn/large.mp4"   # large > medium > small > tiny
    assert clip.page_url == "https://pixabay.com/videos/rain-333/"
    assert clip.author == "이영희"
    assert clip.duration_sec == 18.0
    assert clip.key == ("pixabay", "333")


@pytest.mark.asyncio
async def test_video_search_sends_key_and_korean_lang(monkeypatch):
    monkeypatch.setenv("PIXABAY_API_KEY", "secret-key")
    spy = []
    await PixabaySource(get_json=_stub(_VIDEO_RESPONSE, spy)).search("빗소리", VIDEO)

    call = spy[0]
    # Pixabay는 헤더가 아니라 쿼리스트링으로 인증한다
    assert call["params"]["key"] == "secret-key"
    assert call["params"]["q"] == "빗소리"
    assert call["params"]["lang"] == "ko"
    assert call["headers"] == {}
    # 영상에는 orientation 파라미터가 없다 — 가로 소재는 ffmpeg crop이 흡수한다
    assert "orientation" not in call["params"]


@pytest.mark.asyncio
async def test_photo_search_sends_vertical_orientation(monkeypatch):
    monkeypatch.setenv("PIXABAY_API_KEY", "k")
    spy = []
    clips = await PixabaySource(get_json=_stub(_PHOTO_RESPONSE, spy)).search("도로", PHOTO)

    assert spy[0]["params"]["orientation"] == "vertical"
    assert spy[0]["params"]["image_type"] == "photo"
    assert clips[0].kind == PHOTO
    assert clips[0].url == "https://cdn/large.jpg"
    assert clips[0].author == "박민수"
    assert (clips[0].width, clips[0].height) == (3000, 4500)
    assert clips[0].duration_sec is None


@pytest.mark.asyncio
async def test_video_hit_without_usable_url_is_skipped(monkeypatch):
    monkeypatch.setenv("PIXABAY_API_KEY", "k")
    payload = {"hits": [{"id": 1, "videos": {"large": {"url": ""}}}]}
    assert await PixabaySource(get_json=_stub(payload)).search("q", VIDEO) == []


@pytest.mark.asyncio
async def test_empty_response_returns_empty_list(monkeypatch):
    monkeypatch.setenv("PIXABAY_API_KEY", "k")
    assert await PixabaySource(get_json=_stub({"hits": []})).search("없는말", VIDEO) == []


@pytest.mark.asyncio
async def test_http_error_propagates(monkeypatch):
    monkeypatch.setenv("PIXABAY_API_KEY", "k")

    async def _boom(url, params, headers):
        raise httpx.HTTPStatusError("429", request=None, response=None)

    with pytest.raises(httpx.HTTPStatusError):
        await PixabaySource(get_json=_boom).search("q", VIDEO)
