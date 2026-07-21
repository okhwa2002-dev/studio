from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str
    jwt_secret: str
    app_timezone: str = "Asia/Seoul"
    storage_backend: str = "local"
    storage_path: str = "./storage"
    log_dir: str = "D:/workspace/ok2020/log/studio"
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
    render_font_size: int = 96


@lru_cache
def get_settings() -> Settings:
    return Settings()
