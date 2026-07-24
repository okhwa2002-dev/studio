from functools import lru_cache

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str
    jwt_secret: str
    app_timezone: str = "Asia/Seoul"
    storage_backend: str = "local"
    storage_path: str = "./storage"
    log_dir: str = "./log/studio"
    cors_origins: list[str] = []
    secure_cookies: bool = False
    log_sql: bool = False
    failed_login_limit: int = 5
    openai_api_key: str = ""
    anthropic_api_key: str = ""
    script_provider: str = "openai"
    voice_provider: str = "edge_tts"
    captions_provider: str = "whisper"
    whisper_model: str = "small"
    render_provider: str = "slideshow"
    render_bg_color: str = "#0f172a"
    render_font: str = "Malgun Gothic"
    render_font_size: int = 30
    # whisper·ffmpeg는 CPU를 포화시킨다. 병렬로 돌려도 서로 느려지기만 하므로 기본 1.
    worker_concurrency: int = 1
    # 스톡 소재(Pexels·Pixabay). 키가 하나도 없으면 stock 렌더러는 validate에서 실패한다.
    pexels_api_key: str = ""
    pixabay_api_key: str = ""
    stock_sources: list[str] = ["pexels", "pixabay"]  # 순서가 폴백 우선순위
    stock_max_bytes: int = 52_428_800                 # 씬당 다운로드 상한 50MB
    stock_timeout_sec: int = 30

    @field_validator("jwt_secret")
    @classmethod
    def _jwt_secret_at_least_32_bytes(cls, value: str) -> str:
        if len(value.encode("utf-8")) < 32:
            raise ValueError("JWT_SECRET must be at least 32 bytes")
        return value


@lru_cache
def get_settings() -> Settings:
    return Settings()
