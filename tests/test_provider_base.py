import pytest

from app.providers.base import Provider, StageContext, StageResult, get_provider
from app.utils.errors import AppError


class _Dummy(Provider):
    stage = "script"
    name = "dummy"

    async def run(self, ctx: StageContext) -> StageResult:
        return StageResult(output={"echo": ctx.topic})


def test_stage_context_defaults():
    ctx = StageContext(topic="주제")
    assert ctx.settings == {}
    assert ctx.inputs == {}
    assert ctx.attempt == 0


@pytest.mark.asyncio
async def test_provider_run_contract():
    result = await _Dummy().run(StageContext(topic="hello"))
    assert isinstance(result, StageResult)
    assert result.output == {"echo": "hello"}


def test_get_provider_unknown_raises_apperror():
    with pytest.raises(AppError) as exc:
        get_provider("script", "does-not-exist")
    assert exc.value.status_code == 500
    assert exc.value.code == "PROVIDER_NOT_FOUND"


def test_stage_context_progress_defaults_to_noop():
    # provider가 진행률을 안 내도 그냥 돌아야 한다 — 계약은 선택적이다.
    ctx = StageContext(topic="주제")
    ctx.on_progress(None, "무시된다")  # 예외가 나면 실패


def test_stage_context_accepts_progress_callback():
    seen = []
    ctx = StageContext(topic="주제", on_progress=lambda p, m: seen.append((p, m)))
    ctx.on_progress(42.0, "받아쓰는 중…")
    assert seen == [(42.0, "받아쓰는 중…")]
