import json
import logging
import time

from pydantic import BaseModel, Field, ValidationInfo, field_validator

from app.config import get_settings
from app.queries import queries

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


# 캐시를 TTL과 명시적 무효화 둘 다로 관리한다. 무효화만 두면 다중 프로세스 배포에서
# 다른 프로세스에 변경이 영원히 닿지 않고, TTL만 두면 관리자가 저장 직후 화면에서
# 이전 값을 본다. 같이 두면 같은 프로세스는 즉시, 다른 프로세스는 최대 30초에 수렴한다.
_TTL_SEC = 30.0
_cache: RuntimeSettings | None = None
_cached_at: float = 0.0
# 무효화가 일어날 때마다 증가한다. get_runtime_settings가 DB를 읽는 동안(await로
# 양보하는 사이) 다른 요청이 설정을 저장하고 invalidate_runtime_settings()를 부르면,
# 재개된 조회는 "저장 이전" 스냅샷을 들고 있는 셈이다. 그걸 그대로 _cache에 쓰면
# 방금 무효화한 값이 최대 30초간 다시 살아난다 — TTL+무효화 설계가 약속한
# "같은 프로세스는 즉시 반영"이 깨진다. 조회 시작 시점의 세대를 기억해뒀다가 끝난
# 뒤 세대가 바뀌었으면 캐시에 쓰지 않고 파싱 결과만 반환한다(다음 호출이 다시 읽는다).
_generation: int = 0


async def get_runtime_settings(conn) -> RuntimeSettings:
    """현재 유효한 런타임 설정. conn은 raw_connection()이 준 asyncpg 커넥션이다."""
    global _cache, _cached_at

    now = time.monotonic()
    if _cache is not None and now - _cached_at < _TTL_SEC:
        return _cache

    gen = _generation  # DB 조회 전에 세대를 찍어둔다 — 조회 중 무효화 여부를 나중에 비교한다.
    try:
        # select_all_settings는 suffix 없는 "여러 행" 쿼리라 asyncpg 드라이버에서
        # 비동기 제너레이터로 온다 — await가 아니라 async for로 소비한다
        # (app/api/admin_notices.py의 list_notices_for_admin과 같은 패턴).
        rows = [row async for row in queries.select_all_settings(conn)]
    except Exception:
        # DB 장애 시 조용히 .env 기본값으로 진행한다. 캐시에는 남기지 않는다 —
        # 다음 호출이 다시 시도한다.
        logger.warning("시스템 설정 조회에 실패해 기본값으로 진행합니다.", exc_info=True)
        return RuntimeSettings()

    result = RuntimeSettings.from_overrides({row["key"]: row["value"] for row in rows})

    if _generation != gen:
        # 조회하는 동안(await로 양보한 사이) 다른 요청이 값을 저장하고 무효화했다.
        # 지금 만든 result는 그 저장 이전 스냅샷이므로 캐시에 쓰지 않고 반환만 한다.
        return result

    _cache = result
    _cached_at = now
    return _cache


def invalidate_runtime_settings() -> None:
    """설정 저장 직후 호출한다. 같은 프로세스는 다음 조회에서 곧바로 새 값을 본다."""
    global _cache, _cached_at, _generation
    _cache = None
    _cached_at = 0.0
    _generation += 1
