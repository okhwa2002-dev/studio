import pytest
from pydantic import ValidationError

from app.runtime_settings import RuntimeSettings, stage_setting


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


def test_stage_setting_reads_from_dict():
    assert stage_setting({"render_font_size": 99}, "render_font_size") == 99


def test_stage_setting_falls_back_to_default_when_absent():
    """provider 단위 테스트가 ctx.settings를 비워둬도 동작한다."""
    assert stage_setting({}, "render_font_size") == 30
