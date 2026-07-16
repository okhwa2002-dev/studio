from app.providers.base import REGISTRY, get_provider
from app.providers.script.claude import ClaudeScript
from app.providers.script.fake import FakeScript
from app.providers.script.openai import OpenAIScript


def test_registry_has_all_three_script_providers():
    assert set(REGISTRY["script"].keys()) == {"fake", "openai", "claude"}


def test_get_provider_returns_each_type():
    assert isinstance(get_provider("script", "fake"), FakeScript)
    assert isinstance(get_provider("script", "openai"), OpenAIScript)
    assert isinstance(get_provider("script", "claude"), ClaudeScript)
