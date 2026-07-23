import pytest

from app.config import get_settings
from app.providers.render.sources import (
    DEFAULT_QUERY,
    enabled_sources,
    queries_for,
    select_clip,
)
from app.utils.errors import AppError
from app.utils.stock.base import PHOTO, VIDEO, Clip


@pytest.fixture(autouse=True)
def _fresh_settings():
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


def _clip(source, clip_id, kind=VIDEO):
    return Clip(source=source, kind=kind, id=clip_id, url=f"https://cdn/{clip_id}",
                page_url=f"https://page/{clip_id}", author="a", width=1080, height=1920)


class _FakeSource:
    """(query, kind) -> list[Clip] 또는 예외. 호출 순서를 calls에 남긴다."""

    def __init__(self, name, table):
        self.name = name
        self.table = table
        self.calls = []

    async def search(self, query, kind):
        self.calls.append((query, kind))
        result = self.table.get((query, kind))
        if isinstance(result, Exception):
            raise result
        return list(result or [])


# --- queries_for -------------------------------------------------------------

def test_queries_for_orders_on_screen_then_topic_then_default():
    assert queries_for("서울 야경", "도시 여행") == ["서울 야경", "도시 여행", DEFAULT_QUERY]


def test_queries_for_drops_blank_and_duplicate():
    assert queries_for("   ", "도시") == ["도시", DEFAULT_QUERY]
    assert queries_for("도시", "도시") == ["도시", DEFAULT_QUERY]


# --- select_clip -------------------------------------------------------------

@pytest.mark.asyncio
async def test_picks_first_source_video_for_first_query():
    src = _FakeSource("pexels", {("서울", VIDEO): [_clip("pexels", "1")]})
    clip, query = await select_clip([src], ["서울", "도시", DEFAULT_QUERY], set(), 0)

    assert clip.id == "1"
    assert query == "서울"
    assert src.calls == [("서울", VIDEO)]   # 찾았으면 더 뒤지지 않는다


@pytest.mark.asyncio
async def test_relevance_beats_media_kind():
    # 이 계획의 핵심 순서: on_screen 사진이 topic 영상보다 우선한다
    src = _FakeSource("pexels", {
        ("서울", VIDEO): [],
        ("서울", PHOTO): [_clip("pexels", "photo1", PHOTO)],
        ("도시", VIDEO): [_clip("pexels", "video1")],
    })
    clip, query = await select_clip([src], ["서울", "도시", DEFAULT_QUERY], set(), 0)

    assert clip.id == "photo1"
    assert query == "서울"


@pytest.mark.asyncio
async def test_falls_back_to_topic_when_first_query_is_empty_everywhere():
    src = _FakeSource("pexels", {
        ("서울", VIDEO): [], ("서울", PHOTO): [],
        ("도시", VIDEO): [_clip("pexels", "v")],
    })
    clip, query = await select_clip([src], ["서울", "도시", DEFAULT_QUERY], set(), 0)

    assert query == "도시"


@pytest.mark.asyncio
async def test_falls_back_to_second_source_within_same_query_and_kind():
    first = _FakeSource("pexels", {("서울", VIDEO): []})
    second = _FakeSource("pixabay", {("서울", VIDEO): [_clip("pixabay", "p1")]})
    clip, _ = await select_clip([first, second], ["서울"], set(), 0)

    assert clip.source == "pixabay"


@pytest.mark.asyncio
async def test_source_exception_skips_to_next_source():
    # API가 429/5xx를 내도 전체를 실패시키지 않는다
    boom = _FakeSource("pexels", {("서울", VIDEO): RuntimeError("429")})
    ok = _FakeSource("pixabay", {("서울", VIDEO): [_clip("pixabay", "p1")]})
    clip, _ = await select_clip([boom, ok], ["서울"], set(), 0)

    assert clip.source == "pixabay"


@pytest.mark.asyncio
async def test_excludes_already_used_clips():
    src = _FakeSource("pexels", {
        ("서울", VIDEO): [_clip("pexels", "1"), _clip("pexels", "2")],
    })
    clip, _ = await select_clip([src], ["서울"], {("pexels", "1")}, 0)

    assert clip.id == "2"


@pytest.mark.asyncio
async def test_offset_rotates_pick_so_regenerate_yields_different_clip():
    hits = [_clip("pexels", "1"), _clip("pexels", "2"), _clip("pexels", "3")]
    src = _FakeSource("pexels", {("서울", VIDEO): hits})

    assert (await select_clip([src], ["서울"], set(), 0))[0].id == "1"
    assert (await select_clip([src], ["서울"], set(), 1))[0].id == "2"
    assert (await select_clip([src], ["서울"], set(), 4))[0].id == "2"   # 3개를 넘으면 순환


@pytest.mark.asyncio
async def test_all_queries_empty_raises_no_results():
    src = _FakeSource("pexels", {})
    with pytest.raises(AppError) as exc:
        await select_clip([src], ["서울", "도시", DEFAULT_QUERY], set(), 0)

    assert exc.value.code == "STOCK_NO_RESULTS"
    assert exc.value.status_code == 502


# --- enabled_sources ---------------------------------------------------------

def test_enabled_sources_returns_only_keyed_sources_in_config_order(monkeypatch):
    monkeypatch.setenv("PEXELS_API_KEY", "")
    monkeypatch.setenv("PIXABAY_API_KEY", "k")
    assert [s.name for s in enabled_sources()] == ["pixabay"]


def test_enabled_sources_honours_config_order(monkeypatch):
    monkeypatch.setenv("PEXELS_API_KEY", "k1")
    monkeypatch.setenv("PIXABAY_API_KEY", "k2")
    monkeypatch.setenv("STOCK_SOURCES", '["pixabay","pexels"]')
    assert [s.name for s in enabled_sources()] == ["pixabay", "pexels"]


def test_enabled_sources_without_any_key_raises(monkeypatch):
    monkeypatch.setenv("PEXELS_API_KEY", "")
    monkeypatch.setenv("PIXABAY_API_KEY", "")
    with pytest.raises(AppError) as exc:
        enabled_sources()

    assert exc.value.code == "STOCK_API_KEY_MISSING"


def test_enabled_sources_ignores_unknown_source_name(monkeypatch):
    monkeypatch.setenv("PEXELS_API_KEY", "k")
    monkeypatch.setenv("STOCK_SOURCES", '["nope","pexels"]')
    assert [s.name for s in enabled_sources()] == ["pexels"]
