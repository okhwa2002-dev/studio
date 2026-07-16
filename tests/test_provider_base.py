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
