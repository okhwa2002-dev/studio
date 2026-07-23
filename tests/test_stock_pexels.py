import httpx
import pytest

from app.config import get_settings
from app.utils.stock.base import PHOTO, VIDEO
from app.utils.stock.pexels import PexelsSource


@pytest.fixture(autouse=True)
def _fresh_settings():
    # get_settings는 lru_cache라 monkeypatch.setenv가 캐시된 Settings에 반영되지 않는다.
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


_VIDEO_RESPONSE = {
    "videos": [
        {
            "id": 111,
            "url": "https://www.pexels.com/video/seoul-111/",
            "duration": 12,
            "user": {"name": "홍길동"},
            "video_files": [
                {"link": "https://cdn/small.mp4", "width": 640, "height": 360, "file_type": "video/mp4"},
                {"link": "https://cdn/portrait.mp4", "width": 1080, "height": 1920, "file_type": "video/mp4"},
                {"link": "https://cdn/huge.mp4", "width": 2160, "height": 3840, "file_type": "video/mp4"},
            ],
        }
    ]
}

_PHOTO_RESPONSE = {
    "photos": [
        {
            "id": 222,
            "url": "https://www.pexels.com/photo/cafe-222/",
            "photographer": "김철수",
            "width": 4000,
            "height": 6000,
            "src": {"original": "https://cdn/orig.jpg", "large2x": "https://cdn/large2x.jpg"},
        }
    ]
}


def _stub(payload, spy=None):
    async def _get_json(url, params, headers):
        if spy is not None:
            spy.append({"url": url, "params": params, "headers": headers})
        return payload

    return _get_json


@pytest.mark.asyncio
async def test_video_search_maps_to_clip(monkeypatch):
    monkeypatch.setenv("PEXELS_API_KEY", "k")
    clips = await PexelsSource(get_json=_stub(_VIDEO_RESPONSE)).search("서울 야경", VIDEO)

    assert len(clips) == 1
    clip = clips[0]
    assert clip.source == "pexels"
    assert clip.kind == VIDEO
    assert clip.id == "111"
    assert clip.page_url == "https://www.pexels.com/video/seoul-111/"
    assert clip.author == "홍길동"
    assert clip.duration_sec == 12.0
    assert clip.key == ("pexels", "111")


@pytest.mark.asyncio
async def test_video_search_prefers_portrait_1080_over_bigger_landscape(monkeypatch):
    # 세로 > 1080 이상 > 작은 파일 순. 4K 세로(huge)보다 딱 맞는 1080 세로를 고른다.
    monkeypatch.setenv("PEXELS_API_KEY", "k")
    clips = await PexelsSource(get_json=_stub(_VIDEO_RESPONSE)).search("서울 야경", VIDEO)
    assert clips[0].url == "https://cdn/portrait.mp4"
    assert (clips[0].width, clips[0].height) == (1080, 1920)


@pytest.mark.asyncio
async def test_video_search_sends_korean_locale_and_portrait(monkeypatch):
    monkeypatch.setenv("PEXELS_API_KEY", "secret-key")
    spy = []
    await PexelsSource(get_json=_stub(_VIDEO_RESPONSE, spy)).search("서울 야경", VIDEO)

    call = spy[0]
    assert call["params"]["query"] == "서울 야경"
    assert call["params"]["locale"] == "ko-KR"
    assert call["params"]["orientation"] == "portrait"
    # Pexels는 Bearer가 아니라 키를 그대로 Authorization에 넣는다
    assert call["headers"] == {"Authorization": "secret-key"}


@pytest.mark.asyncio
async def test_photo_search_maps_to_clip(monkeypatch):
    monkeypatch.setenv("PEXELS_API_KEY", "k")
    clips = await PexelsSource(get_json=_stub(_PHOTO_RESPONSE)).search("카페", PHOTO)

    assert clips[0].kind == PHOTO
    assert clips[0].url == "https://cdn/orig.jpg"   # 원본 우선 — 크롭 여유가 크다
    assert clips[0].author == "김철수"
    assert clips[0].duration_sec is None


@pytest.mark.asyncio
async def test_empty_response_returns_empty_list(monkeypatch):
    monkeypatch.setenv("PEXELS_API_KEY", "k")
    assert await PexelsSource(get_json=_stub({"videos": []})).search("없는말", VIDEO) == []


@pytest.mark.asyncio
async def test_http_error_propagates(monkeypatch):
    # 소스는 오류를 삼키지 않는다. 소스를 건너뛸지는 폴백 체인(sources.py)이 결정한다.
    monkeypatch.setenv("PEXELS_API_KEY", "k")

    async def _boom(url, params, headers):
        raise httpx.HTTPStatusError("429", request=None, response=None)

    with pytest.raises(httpx.HTTPStatusError):
        await PexelsSource(get_json=_boom).search("q", VIDEO)
