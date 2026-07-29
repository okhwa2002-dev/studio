import pytest

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

# stock_max_bytes/stock_timeout_sec가 ctx.settings에서 오는지는 stage_setting을 직접
# 부르는 것만으로는 이 task의 실제 산출물(StockRender가 그 값을 다운로드 호출까지
# 전달하는지)을 증명하지 못한다 — Task 2에서 이미 검증한 stage_setting 자체의 재검증일
# 뿐이다. 그래서 여기 있던 test_stock_max_bytes_and_timeout_come_from_ctx_settings는 지우고
# tests/test_provider_render_stock.py에 StockRender.run()을 실제로 통과하는 테스트로 옮겼다
# (test_run_downloads_use_max_bytes_and_timeout_from_ctx_settings).
