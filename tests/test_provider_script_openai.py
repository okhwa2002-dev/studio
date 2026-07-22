from types import SimpleNamespace

import pytest

from app.providers.base import StageContext, StageResult
from app.providers.script.openai import OpenAIScript
from app.providers.script.schema import ScriptDraft, ScriptScene
from app.utils.errors import AppError

_DRAFT = ScriptDraft(
    title="바다 거북 — 60초 쇼츠",
    hook="3초 안에 반전을 보여드립니다.",
    scenes=[ScriptScene(index=1, narration="n", on_screen="o")],
    estimated_duration_sec=45,
)


class _FakeCompletions:
    def __init__(self, draft):
        self._draft = draft
        self.calls = []

    async def parse(self, **kwargs):
        self.calls.append(kwargs)
        message = SimpleNamespace(parsed=self._draft)
        return SimpleNamespace(choices=[SimpleNamespace(message=message)])


class _FakeOpenAI:
    def __init__(self, draft):
        self.completions = _FakeCompletions(draft)
        # client.beta.chat.completions.parse 경로를 흉내
        self.beta = SimpleNamespace(chat=SimpleNamespace(completions=self.completions))


@pytest.mark.asyncio
async def test_run_maps_structured_output_to_schema():
    fake = _FakeOpenAI(_DRAFT)
    result = await OpenAIScript(client=fake).run(StageContext(topic="바다 거북"))
    assert isinstance(result, StageResult)
    assert result.output == _DRAFT.model_dump()
    # 모델·주제가 요청에 실렸는지
    call = fake.completions.calls[0]
    assert call["model"] == "gpt-4o-mini"
    assert any("바다 거북" in m["content"] for m in call["messages"])


@pytest.mark.asyncio
async def test_run_passes_regenerate_hint_on_attempt():
    fake = _FakeOpenAI(_DRAFT)
    await OpenAIScript(client=fake).run(StageContext(topic="바다 거북", attempt=1))
    call = fake.completions.calls[0]
    assert any("새로운 각도" in m["content"] for m in call["messages"])


def test_validate_raises_when_key_missing(monkeypatch):
    monkeypatch.setattr(
        "app.providers.script.openai.get_settings",
        lambda: SimpleNamespace(openai_api_key=""),
    )
    with pytest.raises(AppError) as exc:
        OpenAIScript().validate({})
    assert exc.value.code == "OPENAI_API_KEY_MISSING"


def test_validate_passes_when_key_present(monkeypatch):
    monkeypatch.setattr(
        "app.providers.script.openai.get_settings",
        lambda: SimpleNamespace(openai_api_key="sk-test"),
    )
    OpenAIScript().validate({})  # 예외 없음


@pytest.mark.asyncio
async def test_run_raises_script_parse_failed_when_parsed_is_none():
    # 거부/길이 초과 등으로 completion.choices[0].message.parsed가 None인 경우(M-3)
    fake = _FakeOpenAI(None)
    with pytest.raises(AppError) as exc:
        await OpenAIScript(client=fake).run(StageContext(topic="x"))
    assert exc.value.code == "SCRIPT_PARSE_FAILED"


@pytest.mark.asyncio
async def test_run_reports_progress_without_percent():
    # LLM 단일 호출이라 진짜 %가 없다 — percent=None 계약을 고정한다(0 같은 값 발명 금지).
    fake = _FakeOpenAI(_DRAFT)
    seen: list[tuple[float | None, str]] = []
    ctx = StageContext(topic="바다 거북", on_progress=lambda p, m: seen.append((p, m)))
    await OpenAIScript(client=fake).run(ctx)
    assert seen == [(None, "대본을 생성하는 중…")]


def test_real_openai_sdk_exposes_beta_parse_path():
    # M-1: 코드가 가정한 client.beta.chat.completions.parse 경로가 설치된 openai SDK에 실제로 존재하는지 확인.
    # 네트워크 호출 없음 — 생성자 + 속성 존재 여부만 확인.
    import openai

    c = openai.AsyncOpenAI(api_key="x")
    assert hasattr(c.beta.chat.completions, "parse")
