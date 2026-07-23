from app.config import get_settings
from app.utils.stock.base import PHOTO, VIDEO, Clip
from app.utils.stock.base import get_json as _default_get_json

_VIDEO_URL = "https://pixabay.com/api/videos/"
_PHOTO_URL = "https://pixabay.com/api/"
_PER_PAGE = 20          # Pixabay 허용 범위 3~200
_NAME = "pixabay"
_SIZES = ("large", "medium", "small", "tiny")   # 큰 것부터


def _best_video(videos: dict) -> dict | None:
    """가장 큰 해상도부터 실제 url이 있는 첫 항목."""
    for size in _SIZES:
        item = videos.get(size) or {}
        if item.get("url"):
            return item
    return None


def _video_clips(data: dict) -> list[Clip]:
    clips = []
    for hit in data.get("hits") or []:
        item = _best_video(hit.get("videos") or {})
        if item is None:
            continue
        duration = float(hit.get("duration") or 0)
        clips.append(Clip(
            source=_NAME, kind=VIDEO, id=str(hit.get("id", "")),
            url=item["url"], page_url=hit.get("pageURL", ""),
            author=hit.get("user", ""),
            width=item.get("width") or 0, height=item.get("height") or 0,
            duration_sec=duration or None,
        ))
    return clips


def _photo_clips(data: dict) -> list[Clip]:
    clips = []
    for hit in data.get("hits") or []:
        url = hit.get("largeImageURL")
        if not url:
            continue
        clips.append(Clip(
            source=_NAME, kind=PHOTO, id=str(hit.get("id", "")),
            url=url, page_url=hit.get("pageURL", ""),
            author=hit.get("user", ""),
            width=hit.get("imageWidth") or 0, height=hit.get("imageHeight") or 0,
        ))
    return clips


class PixabaySource:
    """Pixabay 무료 API 검색. PexelsSource와 같은 인터페이스라 체인이 둘을 구분하지 않는다."""

    name = _NAME

    def __init__(self, get_json=None):
        # 테스트는 가짜 get_json을 주입해 네트워크 없이 검증한다.
        self._get_json = get_json or _default_get_json

    async def search(self, query: str, kind: str) -> list[Clip]:
        params = {
            "key": get_settings().pixabay_api_key,   # 헤더가 아니라 쿼리스트링 인증
            "q": query,
            "lang": "ko",        # 한국어 검색어 공식 지원
            "per_page": _PER_PAGE,
            "safesearch": "true",
        }
        if kind == VIDEO:
            url = _VIDEO_URL     # 영상에는 orientation이 없다 — crop이 흡수한다
        else:
            url = _PHOTO_URL
            params |= {"image_type": "photo", "orientation": "vertical"}
        data = await self._get_json(url, params, {})
        return _video_clips(data) if kind == VIDEO else _photo_clips(data)
