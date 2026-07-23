import logging

from app.config import get_settings
from app.utils.errors import AppError
from app.utils.stock.base import PHOTO, VIDEO, Clip
from app.utils.stock.pexels import PexelsSource
from app.utils.stock.pixabay import PixabaySource

logger = logging.getLogger(__name__)

DEFAULT_QUERY = "abstract background"   # 최후 폴백 — 이게 0건일 일은 사실상 없다
_KINDS = (VIDEO, PHOTO)                 # 영상 우선, 없으면 이미지
_FACTORIES = {
    "pexels": (PexelsSource, "pexels_api_key"),
    "pixabay": (PixabaySource, "pixabay_api_key"),
}


def enabled_sources() -> list:
    """STOCK_SOURCES 순서대로, API 키가 실제로 있는 소스만 만든다.

    키가 하나만 있어도 그 소스로 동작한다. 하나도 없을 때만 실패한다.
    """
    settings = get_settings()
    sources = []
    for name in settings.stock_sources:
        entry = _FACTORIES.get(name)
        if entry is None:
            logger.warning("알 수 없는 STOCK_SOURCES 항목이라 건너뜁니다: %s", name)
            continue
        factory, key_field = entry
        if getattr(settings, key_field, ""):
            sources.append(factory())
    if not sources:
        raise AppError(400, "STOCK_API_KEY_MISSING",
                       "스톡 API 키가 없습니다. PEXELS_API_KEY 또는 PIXABAY_API_KEY를 설정해 주세요.")
    return sources


def queries_for(on_screen: str, topic: str) -> list[str]:
    """검색어 우선순위. 빈 문자열과 중복은 뺀다."""
    ordered = []
    for query in ((on_screen or "").strip(), (topic or "").strip(), DEFAULT_QUERY):
        if query and query not in ordered:
            ordered.append(query)
    return ordered


async def select_clip(sources, queries: list[str], used_keys: set, offset: int) -> tuple[Clip, str]:
    """폴백 체인으로 소재 1건을 고른다. (클립, 실제로 먹힌 검색어)를 돌려준다.

    루프 순서가 곧 우선순위다: 관련성(query) > 매체(kind) > 출처(source).
    on_screen으로 사진밖에 없다면, 그 사진이 topic으로 찾은 무관한 영상보다 낫다.
    이 순서를 kind 우선이나 source 우선으로 바꾸면 우선순위 자체가 조용히 뒤바뀌니
    최적화한답시고 루프를 재배치하지 말 것.

    offset은 ctx.attempt + 씬 번호다 — [재생성]하면 같은 검색 결과에서 다른 클립이 나온다.
    """
    for query in queries:
        for kind in _KINDS:
            for source in sources:
                try:
                    hits = await source.search(query, kind)
                except Exception:
                    # 4xx·5xx·네트워크 오류는 이 소스만 건너뛴다. 전부 실패해야 아래 STOCK_NO_RESULTS.
                    logger.warning("스톡 검색 실패 — 다음 소스로: source=%s query=%s kind=%s",
                                   source.name, query, kind, exc_info=True)
                    continue
                fresh = [clip for clip in hits if clip.key not in used_keys]
                if fresh:
                    return fresh[offset % len(fresh)], query
    raise AppError(502, "STOCK_NO_RESULTS",
                   "배경 소재를 찾지 못했습니다. 대본의 화면 문구를 바꿔 보세요.")
