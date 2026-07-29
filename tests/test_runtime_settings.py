import pytest
from pydantic import ValidationError

from app.config import get_settings
from app.runtime_settings import (
    EnvSettingsError,
    RuntimeSettings,
    check_env_defaults,
    stage_setting,
)


@pytest.fixture
def bad_env(monkeypatch):
    """.env 값을 범위 밖으로 바꾼 뒤 lru_cache를 비워 실제로 반영시킨다.

    conftest.py가 9개 값을 전부 범위 안으로 못박아두기 때문에, "범위 밖 .env"라는
    결함은 일부러 이렇게 넣지 않으면 스위트에 구조적으로 보이지 않는다.
    """

    def _set(**pairs: str) -> None:
        for key, value in pairs.items():
            monkeypatch.setenv(key, value)
        get_settings.cache_clear()

    yield _set
    # monkeypatch는 env는 되돌려주지만 lru_cache는 못 비운다. 여기서 직접 되돌리지
    # 않으면 다음 테스트가 오염된 Settings를 그대로 물려받는다.
    monkeypatch.undo()
    get_settings.cache_clear()


def test_defaults_come_from_env():
    """DB 오버라이드가 없으면 .env(conftest가 고정한 값)가 그대로 유효값이다."""
    rs = RuntimeSettings()
    assert rs.script_provider == "fake"      # conftest.py가 SCRIPT_PROVIDER=fake로 고정
    assert rs.whisper_model == "small"
    assert rs.failed_login_limit == 5
    assert rs.password_min_len == 8
    assert rs.signup_auto_approve is False


def test_override_beats_default():
    rs = RuntimeSettings.from_overrides({"render_font_size": "42"})
    assert rs.render_font_size == 42
    assert rs.whisper_model == "small"       # 안 건드린 키는 기본값 유지


def test_unknown_key_is_ignored():
    rs = RuntimeSettings.from_overrides({"legacy_removed_key": '"whatever"'})
    assert not hasattr(rs, "legacy_removed_key")
    assert rs.render_font_size == 30


def test_corrupt_value_falls_back_to_default():
    """JSON이 깨진 행 하나가 앱 전체를 멈추게 하지 않는다."""
    rs = RuntimeSettings.from_overrides({"render_font_size": "not-json{"})
    assert rs.render_font_size == 30


def test_bool_and_list_round_trip():
    rs = RuntimeSettings.from_overrides(
        {"signup_auto_approve": "true", "stock_sources": '["pixabay"]'}
    )
    assert rs.signup_auto_approve is True
    assert rs.stock_sources == ["pixabay"]


def test_password_min_len_cannot_go_below_8():
    """설정으로 열되 지금 수준 아래로는 못 내린다 — 보안이 후퇴하는 경로를 만들지 않는다."""
    with pytest.raises(ValidationError):
        RuntimeSettings(password_min_len=4)


def test_render_font_size_range_is_enforced():
    with pytest.raises(ValidationError):
        RuntimeSettings(render_font_size=0)
    with pytest.raises(ValidationError):
        RuntimeSettings(render_font_size=500)


def test_bg_color_must_be_hex():
    with pytest.raises(ValidationError):
        RuntimeSettings(render_bg_color="navy")
    assert RuntimeSettings(render_bg_color="#ABCDEF").render_bg_color == "#ABCDEF"


def test_unknown_provider_is_rejected():
    with pytest.raises(ValidationError):
        RuntimeSettings(script_provider="gpt5-turbo-ultra")


def test_known_provider_is_accepted():
    assert RuntimeSettings(script_provider="claude").script_provider == "claude"


def test_stock_sources_rejects_empty_and_duplicates():
    with pytest.raises(ValidationError):
        RuntimeSettings(stock_sources=[])
    with pytest.raises(ValidationError):
        RuntimeSettings(stock_sources=["pexels", "pexels"])


def test_out_of_range_env_default_is_rejected(bad_env):
    """범위 밖 .env가 조용히 유효값이 되면 안 된다.

    이 단언이 없으면 validate_default=True를 지워도 스위트가 통과한다 — 그 상태에서는
    PASSWORD_MIN_LEN=4가 실효 하한이 되고(하한 8 약속이 .env 경로에서 깨진다),
    GET이 내려준 검증 안 된 값을 화면이 그대로 PUT해 아무 설정도 저장할 수 없게 된다.
    """
    bad_env(PASSWORD_MIN_LEN="4")
    with pytest.raises(ValidationError):
        RuntimeSettings()


def test_check_env_defaults_names_the_offending_keys(bad_env):
    """기동 실패 메시지는 고쳐야 할 .env 키와 허용 범위를 담아야 한다.

    ge·le만 검증하는 테스트가 따로 없던 failed_login_limit·stock_max_bytes·
    stock_timeout_sec 세 항목을 여기서 함께 덮는다(제약을 지우면 이 테스트가 깨진다).
    """
    bad_env(STOCK_TIMEOUT_SEC="600", FAILED_LOGIN_LIMIT="0", STOCK_MAX_BYTES="1024")

    with pytest.raises(EnvSettingsError) as exc_info:
        check_env_defaults()

    message = str(exc_info.value)
    assert "STOCK_TIMEOUT_SEC" in message
    assert "FAILED_LOGIN_LIMIT" in message
    assert "STOCK_MAX_BYTES" in message
    assert "300" in message  # le=300이라는 허용 범위가 메시지에 드러난다


def test_check_env_defaults_passes_for_valid_env():
    """정상 .env에서는 기동을 막지 않는다."""
    check_env_defaults()


def test_stage_setting_reads_from_dict():
    assert stage_setting({"render_font_size": 99}, "render_font_size") == 99


def test_stage_setting_falls_back_to_default_when_absent():
    """provider 단위 테스트가 ctx.settings를 비워둬도 동작한다."""
    assert stage_setting({}, "render_font_size") == 30
