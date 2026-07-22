import importlib

import app.config as config_module


def test_settings_loads_from_env(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "postgresql+asyncpg://u:p@localhost:5432/studio")
    monkeypatch.setenv("JWT_SECRET", "test-secret")
    importlib.reload(config_module)
    config_module.get_settings.cache_clear()

    s = config_module.get_settings()
    assert s.database_url == "postgresql+asyncpg://u:p@localhost:5432/studio"
    assert s.jwt_secret == "test-secret"
    assert s.app_timezone == "Asia/Seoul"      # 기본값
    assert s.storage_backend == "local"        # 기본값
    assert s.secure_cookies is False           # 기본값


def test_render_settings_defaults(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "postgresql+asyncpg://u:p@localhost:5432/studio")
    monkeypatch.setenv("JWT_SECRET", "test-secret")
    monkeypatch.delenv("RENDER_PROVIDER", raising=False)
    importlib.reload(config_module)
    config_module.get_settings.cache_clear()

    s = config_module.get_settings()
    assert s.render_provider == "slideshow"
    assert s.render_bg_color == "#0f172a"
    assert s.render_font == "Malgun Gothic"
    assert s.render_font_size == 30


def test_worker_concurrency_defaults_to_one(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "postgresql+asyncpg://u:p@localhost:5432/studio")
    monkeypatch.setenv("JWT_SECRET", "test-secret")
    monkeypatch.delenv("WORKER_CONCURRENCY", raising=False)
    importlib.reload(config_module)
    config_module.get_settings.cache_clear()

    assert config_module.get_settings().worker_concurrency == 1
