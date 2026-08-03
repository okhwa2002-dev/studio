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
    # 비밀번호 최소 길이. 관리자가 시스템 설정에서 올릴 수 있고, 8 밑으로는 못 내린다.
    password_min_len: int = 8
    # 참이면 가입 즉시 ACTIVE. 거짓이면 관리자 승인 대기(PENDING).
    signup_auto_approve: bool = False
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

    # --- 이메일(SMTP) ---
    # SMTP_HOST가 비어 있으면 메일을 보내지 않고 LOG_DIR/mail/*.eml로 저장한다(개발용 폴백).
    # 이 키 하나가 모드 스위치다 — 운영에서 빠뜨리면 기동 로그에 경고가 남는다(app/main.py).
    smtp_host: str = ""
    smtp_port: int = 587
    # 인증 없는 사내 릴레이도 있으므로 빈 값을 허용한다(빈 값이면 인증을 시도하지 않는다).
    smtp_user: str = ""
    smtp_password: str = ""
    # 발신자. 비면 smtp_user를 쓴다. "Studio <no-reply@x.com>" 형식도 그대로 넣을 수 있어
    # 표시 이름을 위한 별도 키를 두지 않는다.
    smtp_from: str = ""
    # 셋 중 하나. 불리언 두 개(use_tls/use_starttls)로 쪼개면 "둘 다 참"처럼 성립할 수
    # 없는 조합이 표현된다.
    smtp_tls: str = "starttls"
    # 백그라운드로 돌더라도 무한정 매달리지 않게 한다.
    smtp_timeout_sec: int = 15

    @field_validator("jwt_secret")
    @classmethod
    def _jwt_secret_at_least_32_bytes(cls, value: str) -> str:
        if len(value.encode("utf-8")) < 32:
            raise ValueError("JWT_SECRET must be at least 32 bytes")
        return value

    @field_validator("smtp_tls")
    @classmethod
    def _known_smtp_tls(cls, value: str) -> str:
        allowed = ("starttls", "ssl", "none")
        if value not in allowed:
            raise ValueError(f"SMTP_TLS는 {' | '.join(allowed)} 중 하나여야 합니다: {value}")
        return value


@lru_cache
def get_settings() -> Settings:
    return Settings()
