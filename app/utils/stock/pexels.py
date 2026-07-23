from app.config import get_settings
from app.utils.stock.base import PHOTO, VIDEO, Clip
from app.utils.stock.base import get_json as _default_get_json

# 문서상 경로. 스모크(Task 10)에서 404가 나면 "https://api.pexels.com/videos/search"로 바꾼다.
_VIDEO_URL = "https://api.pexels.com/v1/videos/search"
_PHOTO_URL = "https://api.pexels.com/v1/search"
_PER_PAGE = 15
_NAME = "pexels"


def _best_file(files: list[dict]) -> dict | None:
    """세로 > 짧은 변 1080 이상 > 파일 작은 순. 세로 원본이 있으면 크롭 손실이 없다."""
    usable = [f for f in files if f.get("link") and f.get("width") and f.get("height")]
    if not usable:
        return None

    def score(f: dict) -> tuple[int, int, int]:
        return (
            1 if f["height"] > f["width"] else 0,
            1 if min(f["width"], f["height"]) >= 1080 else 0,
            -(f["width"] * f["height"]),   # 조건이 같으면 작은 파일 (다운로드 절약)
        )

    return max(usable, key=score)


def _video_clips(data: dict) -> list[Clip]:
    clips = []
    for hit in data.get("videos") or []:
        file = _best_file(hit.get("video_files") or [])
        if file is None:
            continue
        duration = float(hit.get("duration") or 0)
        clips.append(Clip(
            source=_NAME, kind=VIDEO, id=str(hit.get("id", "")),
            url=file["link"], page_url=hit.get("url", ""),
            author=(hit.get("user") or {}).get("name", ""),
            width=file["width"], height=file["height"],
            duration_sec=duration or None,
        ))
    return clips


def _photo_clips(data: dict) -> list[Clip]:
    clips = []
    for hit in data.get("photos") or []:
        src = hit.get("src") or {}
        # 원본 우선 — 9:16으로 크롭할 여유가 크다. 상한 초과는 다운로드 단계가 거른다.
        url = src.get("original") or src.get("large2x")
        if not url:
            continue
        clips.append(Clip(
            source=_NAME, kind=PHOTO, id=str(hit.get("id", "")),
            url=url, page_url=hit.get("url", ""),
            author=hit.get("photographer", ""),
            width=hit.get("width") or 0, height=hit.get("height") or 0,
        ))
    return clips


class PexelsSource:
    """Pexels 무료 API 검색. HTTP 오류는 삼키지 않는다 — 소스를 건너뛸지는 호출자가 정한다."""

    name = _NAME

    def __init__(self, get_json=None):
        # 테스트는 가짜 get_json을 주입해 네트워크 없이 검증한다.
        self._get_json = get_json or _default_get_json

    async def search(self, query: str, kind: str) -> list[Clip]:
        url = _VIDEO_URL if kind == VIDEO else _PHOTO_URL
        params = {
            "query": query,
            "per_page": _PER_PAGE,
            "orientation": "portrait",
            "locale": "ko-KR",   # 한국어 검색어 공식 지원
        }
        headers = {"Authorization": get_settings().pexels_api_key}
        data = await self._get_json(url, params, headers)
        return _video_clips(data) if kind == VIDEO else _photo_clips(data)
