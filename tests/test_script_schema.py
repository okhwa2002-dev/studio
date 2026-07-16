from app.config import Settings
from app.providers.script.prompts import system_prompt, user_prompt
from app.providers.script.schema import ScriptDraft, ScriptScene


def test_settings_has_provider_fields(monkeypatch):
    # conftest가 통합 테스트를 위해 SCRIPT_PROVIDER=fake를 프로세스 전역 env에 설정하므로,
    # 여기서는 그 영향을 배제하고 진짜 클래스 기본값(openai)을 검증한다.
    monkeypatch.delenv("SCRIPT_PROVIDER", raising=False)
    s = Settings(database_url="postgresql+asyncpg://x", jwt_secret="secret-secret-secret-32bytes!!")
    assert s.script_provider == "openai"       # 기본값
    assert s.openai_api_key == ""
    assert s.anthropic_api_key == ""


def test_script_draft_shape():
    draft = ScriptDraft(
        title="t",
        hook="h",
        scenes=[ScriptScene(index=1, narration="n", on_screen="o")],
        estimated_duration_sec=45,
    )
    dumped = draft.model_dump()
    assert set(dumped.keys()) == {"title", "hook", "scenes", "estimated_duration_sec"}
    assert set(dumped["scenes"][0].keys()) == {"index", "narration", "on_screen"}


def test_user_prompt_adds_regenerate_hint():
    assert "새로운 각도" not in user_prompt("바다 거북", attempt=0)
    assert "새로운 각도" in user_prompt("바다 거북", attempt=1)
    assert "바다 거북" in user_prompt("바다 거북", attempt=0)
    assert isinstance(system_prompt(), str) and system_prompt()
