from types import SimpleNamespace

import pytest

from app.providers.base import StageContext, StageResult
from app.providers.script.claude import ClaudeScript
from app.providers.script.schema import ScriptDraft, ScriptScene
from app.utils.errors import AppError

_DRAFT = ScriptDraft(
    title="바다 거북 — 60초 쇼츠",
    hook="3초 안에 반전을 보여드립니다.",
    scenes=[ScriptScene(index=1, narration="n", on_screen="o")],
    estimated_duration_sec=45,
)


class _FakeMessages:
    def __init__(self, draft):
        self._draft = draft
        self.calls = []

    async def parse(self, **kwargs):
        self.calls.append(kwargs)
        return SimpleNamespace(parsed_output=self._draft)


class _FakeAnthropic:
    def __init__(self, draft):
        self.messages = _FakeMessages(draft)


@pytest.mark.asyncio
async def test_run_maps_structured_output_to_schema():
    fake = _FakeAnthropic(_DRAFT)
    result = await ClaudeScript(client=fake).run(StageContext(topic="바다 거북"))
    assert isinstance(result, StageResult)
    assert result.output == _DRAFT.model_dump()
    call = fake.messages.calls[0]
    assert call["model"] == "claude-haiku-4-5"
    assert any("바다 거북" in m["content"] for m in call["messages"])


@pytest.mark.asyncio
async def test_run_passes_regenerate_hint_on_attempt():
    fake = _FakeAnthropic(_DRAFT)
    await ClaudeScript(client=fake).run(StageContext(topic="바다 거북", attempt=2))
    call = fake.messages.calls[0]
    assert any("새로운 각도" in m["content"] for m in call["messages"])


def test_validate_raises_when_key_missing(monkeypatch):
    monkeypatch.setattr(
        "app.providers.script.claude.get_settings",
        lambda: SimpleNamespace(anthropic_api_key=""),
    )
    with pytest.raises(AppError) as exc:
        ClaudeScript().validate({})
    assert exc.value.code == "ANTHROPIC_API_KEY_MISSING"


def test_validate_passes_when_key_present(monkeypatch):
    monkeypatch.setattr(
        "app.providers.script.claude.get_settings",
        lambda: SimpleNamespace(anthropic_api_key="sk-ant-test"),
    )
    ClaudeScript().validate({})


@pytest.mark.asyncio
async def test_run_raises_script_parse_failed_when_parsed_output_is_none():
    # 거부/max_tokens 등으로 message.parsed_output이 None인 경우(M-3)
    fake = _FakeAnthropic(None)
    with pytest.raises(AppError) as exc:
        await ClaudeScript(client=fake).run(StageContext(topic="x"))
    assert exc.value.code == "SCRIPT_PARSE_FAILED"


@pytest.mark.asyncio
async def test_run_reports_progress_without_percent():
    # LLM 단일 호출이라 진짜 %가 없다 — percent=None 계약을 고정한다(0 같은 값 발명 금지).
    fake = _FakeAnthropic(_DRAFT)
    seen: list[tuple[float | None, str]] = []
    ctx = StageContext(topic="바다 거북", on_progress=lambda p, m: seen.append((p, m)))
    await ClaudeScript(client=fake).run(ctx)
    assert seen == [(None, "대본을 생성하는 중…")]
