import json
import logging

from pydantic import BaseModel, Field, ValidationInfo, field_validator

from app.config import get_settings

logger = logging.getLogger(__name__)

_HEX_COLOR = r"^#[0-9a-fA-F]{6}$"
_WHISPER_MODELS = ("tiny", "base", "small", "medium", "large-v3")
_STOCK_SOURCES = ("pexels", "pixabay")


class RuntimeSettings(BaseModel):
    """관리자가 화면에서 바꿀 수 있는 설정.

    필드 정의가 곧 화이트리스트·타입·범위다. 기본값은 default_factory로 .env에서
    읽는다 — 인스턴스를 만들 때 평가되므로 테스트가 env를 바꿔도 따라온다.
    """

    # --- 파이프라인 기본값 ---
    script_provider: str = Field(default_factory=lambda: get_settings().script_provider)
    voice_provider: str = Field(default_factory=lambda: get_settings().voice_provider)
    captions_provider: str = Field(default_factory=lambda: get_settings().captions_provider)
    render_provider: str = Field(default_factory=lambda: get_settings().render_provider)
    whisper_model: str = Field(default_factory=lambda: get_settings().whisper_model)
    render_bg_color: str = Field(
        default_factory=lambda: get_settings().render_bg_color, pattern=_HEX_COLOR
    )
    render_font: str = Field(
        default_factory=lambda: get_settings().render_font, min_length=1, max_length=100
    )
    render_font_size: int = Field(
        default_factory=lambda: get_settings().render_font_size, ge=8, le=200
    )
    stock_sources: list[str] = Field(default_factory=lambda: get_settings().stock_sources)
    stock_max_bytes: int = Field(
        default_factory=lambda: get_settings().stock_max_bytes,
        ge=1_048_576, le=524_288_000,          # 1MB ~ 500MB
    )
    stock_timeout_sec: int = Field(
        default_factory=lambda: get_settings().stock_timeout_sec, ge=5, le=300
    )

    # --- 계정 · 보안 ---
    failed_login_limit: int = Field(
        default_factory=lambda: get_settings().failed_login_limit, ge=1, le=100
    )
    # 하한 8은 협상 대상이 아니다. 관리자 실수로 보안이 후퇴하는 경로를 만들지 않는다.
    password_min_len: int = Field(
        default_factory=lambda: get_settings().password_min_len, ge=8, le=128
    )
    signup_auto_approve: bool = Field(
        default_factory=lambda: get_settings().signup_auto_approve
    )

    @field_validator("script_provider", "voice_provider", "captions_provider", "render_provider")
    @classmethod
    def _known_provider(cls, value: str, info: ValidationInfo) -> str:
        # 선택지를 손으로 적지 않고 REGISTRY에서 가져온다 — provider를 추가하면
        # 설정 선택지가 자동으로 따라온다.
        #
        # 이 import는 반드시 함수 안에 둔다. provider들이 stage_setting을 쓰려고 이
        # 모듈을 import하는데, app/providers/base.py는 파일 하단에서 그 provider들을
        # 다시 import한다. 모듈 최상단에서 REGISTRY를 가져오면 순환 import가 닫혀
        # "partially initialized module" ImportError가 난다.
        from app.providers.base import REGISTRY

        stage = info.field_name.removesuffix("_provider")
        allowed = REGISTRY.get(stage, {})
        if value not in allowed:
            raise ValueError(f"알 수 없는 provider입니다: {value} (가능: {', '.join(allowed)})")
        return value

    @field_validator("whisper_model")
    @classmethod
    def _known_whisper_model(cls, value: str) -> str:
        if value not in _WHISPER_MODELS:
            raise ValueError(f"알 수 없는 모델입니다: {value} (가능: {', '.join(_WHISPER_MODELS)})")
        return value

    @field_validator("stock_sources")
    @classmethod
    def _valid_stock_sources(cls, value: list[str]) -> list[str]:
        if not value:
            raise ValueError("스톡 소스를 하나 이상 선택해 주세요.")
        if len(set(value)) != len(value):
            raise ValueError("스톡 소스가 중복되었습니다.")
        unknown = [v for v in value if v not in _STOCK_SOURCES]
        if unknown:
            raise ValueError(f"알 수 없는 스톡 소스입니다: {', '.join(unknown)}")
        return value

    @classmethod
    def from_overrides(cls, overrides: dict[str, str]) -> "RuntimeSettings":
        """DB에서 읽은 {key: JSON 문자열}을 .env 기본값 위에 덮어쓴다.

        모르는 키는 무시하고(예전 설정이 남아 있어도 안전), 깨진 값은 경고만
        남기고 건너뛴다(행 하나가 앱 전체를 멈추게 하지 않는다).
        """
        parsed: dict = {}
        for key, raw in overrides.items():
            if key not in cls.model_fields:
                continue
            try:
                parsed[key] = json.loads(raw)
            except (TypeError, ValueError):
                logger.warning("시스템 설정 값을 해석할 수 없어 기본값을 씁니다: %s", key)
        try:
            return cls(**parsed)
        except Exception:
            # 범위를 벗어난 값이 어떤 경로로든 DB에 들어간 경우. 전부 기본값으로 후퇴한다.
            logger.warning("시스템 설정이 유효하지 않아 기본값을 씁니다.", exc_info=True)
            return cls()


def stage_setting(settings: dict, key: str):
    """ctx.settings에서 런타임 설정값을 읽는다.

    파이프라인이 항상 주입하지만, provider 단위 테스트는 ctx.settings를 비워둘 수
    있으므로 .env 기본값으로 폴백한다.
    """
    if key in settings:
        return settings[key]
    return getattr(RuntimeSettings(), key)
