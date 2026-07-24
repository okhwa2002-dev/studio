import pytest
from pydantic import ValidationError

import app.config as config_module

SAFE_JWT_SECRET = "test-jwt-secret-that-is-32-bytes!"


def test_cached_test_settings_use_safe_jwt_secret():
    assert len(config_module.get_settings().jwt_secret.encode("utf-8")) >= 32


def test_settings_loads_from_env(monkeypatch):
    # env var가 실제로 반영되는지가 요지다. .env는 꺼서 개발자 로컬 값이 섞이지 않게 한다.
    monkeypatch.setenv("DATABASE_URL", "postgresql+asyncpg://u:p@localhost:5432/studio")
    monkeypatch.setenv("JWT_SECRET", SAFE_JWT_SECRET)

    s = config_module.Settings(_env_file=None)
    assert s.database_url == "postgresql+asyncpg://u:p@localhost:5432/studio"
    assert s.jwt_secret == SAFE_JWT_SECRET
    assert s.app_timezone == "Asia/Seoul"      # 기본값
    assert s.storage_backend == "local"        # 기본값
    assert s.secure_cookies is False           # 기본값


def test_jwt_secret_rejects_fewer_than_32_bytes(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "postgresql+asyncpg://u:p@localhost:5432/studio")
    monkeypatch.setenv("JWT_SECRET", "x" * 31)

    with pytest.raises(ValidationError, match="JWT_SECRET must be at least 32 bytes"):
        config_module.Settings(_env_file=None)


def test_jwt_secret_accepts_exactly_32_bytes(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "postgresql+asyncpg://u:p@localhost:5432/studio")
    monkeypatch.setenv("JWT_SECRET", "x" * 32)

    assert config_module.Settings(_env_file=None).jwt_secret == "x" * 32


def test_jwt_secret_measures_utf8_bytes(monkeypatch):
    secret = "가" * 11
    monkeypatch.setenv("DATABASE_URL", "postgresql+asyncpg://u:p@localhost:5432/studio")
    monkeypatch.setenv("JWT_SECRET", secret)

    assert config_module.Settings(_env_file=None).jwt_secret == secret


def test_render_settings_defaults(monkeypatch):
    # 코드 기본값 검증이라 값이 올 수 있는 두 소스를 모두 막아야 한다:
    #   delenv        → conftest가 심어둔 os.environ["RENDER_PROVIDER"]="fake"
    #   _env_file=None → 개발자의 실제 .env (예: RENDER_PROVIDER=stock). delenv로는 못 막는다.
    monkeypatch.setenv("DATABASE_URL", "postgresql+asyncpg://u:p@localhost:5432/studio")
    monkeypatch.setenv("JWT_SECRET", SAFE_JWT_SECRET)
    monkeypatch.delenv("RENDER_PROVIDER", raising=False)

    s = config_module.Settings(_env_file=None)
    assert s.render_provider == "slideshow"
    assert s.render_bg_color == "#0f172a"
    assert s.render_font == "Malgun Gothic"
    assert s.render_font_size == 30


def test_worker_concurrency_defaults_to_one(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "postgresql+asyncpg://u:p@localhost:5432/studio")
    monkeypatch.setenv("JWT_SECRET", SAFE_JWT_SECRET)
    monkeypatch.delenv("WORKER_CONCURRENCY", raising=False)

    assert config_module.Settings(_env_file=None).worker_concurrency == 1


def test_stock_settings_defaults(monkeypatch):
    # app/config.py의 Settings는 env_file=".env"를 별도 소스로 읽기 때문에
    # monkeypatch.delenv만으로는 개발자의 실제 .env 값(예: PEXELS_API_KEY)을 가릴 수 없다.
    # _env_file=None으로 .env 로딩 자체를 끄고 Settings를 직접 생성해 격리한다.
    # (DATABASE_URL·JWT_SECRET은 기본값이 없는 필수 필드라 env로 채워줘야 한다)
    monkeypatch.setenv("DATABASE_URL", "postgresql+asyncpg://u:p@localhost:5432/studio")
    monkeypatch.setenv("JWT_SECRET", SAFE_JWT_SECRET)

    s = config_module.Settings(_env_file=None)
    assert s.pexels_api_key == ""
    assert s.pixabay_api_key == ""
    assert s.stock_sources == ["pexels", "pixabay"]   # 순서가 폴백 우선순위
    assert s.stock_max_bytes == 52_428_800            # 50MB
    assert s.stock_timeout_sec == 30


def test_stock_sources_parsed_from_json_env(monkeypatch):
    # CORS_ORIGINS와 같은 JSON 배열 표기. 순서를 바꿔 Pixabay를 먼저 쓸 수 있어야 한다.
    # _env_file=None은 .env 파일 로딩만 끄고 os.environ은 그대로 읽으므로
    # monkeypatch.setenv로 넣은 STOCK_SOURCES는 여전히 적용된다.
    monkeypatch.setenv("DATABASE_URL", "postgresql+asyncpg://u:p@localhost:5432/studio")
    monkeypatch.setenv("JWT_SECRET", SAFE_JWT_SECRET)
    monkeypatch.setenv("STOCK_SOURCES", '["pixabay"]')

    s = config_module.Settings(_env_file=None)
    assert s.stock_sources == ["pixabay"]
