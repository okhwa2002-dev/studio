import pytest

from app.providers.base import StageContext
from app.providers.render.sources import enabled_sources
from app.utils.errors import AppError


def test_enabled_sources_uses_given_order(monkeypatch):
    from app.config import get_settings

    monkeypatch.setattr(get_settings(), "pexels_api_key", "k1", raising=False)
    monkeypatch.setattr(get_settings(), "pixabay_api_key", "k2", raising=False)

    names = [type(s).__name__ for s in enabled_sources(["pixabay", "pexels"])]
    assert names == ["PixabaySource", "PexelsSource"]


def test_enabled_sources_falls_back_to_env_when_none(monkeypatch):
    from app.config import get_settings

    monkeypatch.setattr(get_settings(), "pexels_api_key", "k1", raising=False)
    monkeypatch.setattr(get_settings(), "pixabay_api_key", "", raising=False)

    names = [type(s).__name__ for s in enabled_sources()]
    assert names == ["PexelsSource"]


def test_enabled_sources_still_requires_at_least_one_api_key(monkeypatch):
    from app.config import get_settings

    monkeypatch.setattr(get_settings(), "pexels_api_key", "", raising=False)
    monkeypatch.setattr(get_settings(), "pixabay_api_key", "", raising=False)

    with pytest.raises(AppError) as exc:
        enabled_sources(["pexels", "pixabay"])
    assert exc.value.code == "STOCK_API_KEY_MISSING"


def test_stock_max_bytes_and_timeout_come_from_ctx_settings():
    from app.runtime_settings import stage_setting

    ctx = StageContext(
        topic="주제",
        settings={"stock_max_bytes": 1_048_576, "stock_timeout_sec": 7},
        workdir="projects/1/render",
    )
    assert stage_setting(ctx.settings, "stock_max_bytes") == 1_048_576
    assert stage_setting(ctx.settings, "stock_timeout_sec") == 7
