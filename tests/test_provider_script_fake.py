import pytest

from app.providers.base import StageContext, StageResult
from app.providers.script.fake import FakeScript


@pytest.mark.asyncio
async def test_output_schema():
    result = await FakeScript().run(StageContext(topic="바다 거북"))
    assert isinstance(result, StageResult)
    out = result.output
    assert out["title"].startswith("바다 거북")
    assert isinstance(out["hook"], str) and out["hook"]
    assert isinstance(out["scenes"], list) and len(out["scenes"]) >= 1
    first = out["scenes"][0]
    assert set(first.keys()) == {"index", "narration", "on_screen"}
    assert first["index"] == 1
    assert isinstance(out["estimated_duration_sec"], int) and out["estimated_duration_sec"] > 0


@pytest.mark.asyncio
async def test_deterministic_for_same_topic_and_attempt():
    a = await FakeScript().run(StageContext(topic="주제", attempt=0))
    b = await FakeScript().run(StageContext(topic="주제", attempt=0))
    assert a.output == b.output


@pytest.mark.asyncio
async def test_regeneration_changes_output():
    a = await FakeScript().run(StageContext(topic="주제", attempt=0))
    b = await FakeScript().run(StageContext(topic="주제", attempt=1))
    assert a.output != b.output


@pytest.mark.asyncio
async def test_run_reports_progress_without_percent():
    # LLM 단일 호출이라 진짜 %가 없다 — percent=None 계약을 고정한다(0 같은 값 발명 금지).
    seen: list[tuple[float | None, str]] = []
    ctx = StageContext(topic="바다 거북", on_progress=lambda p, m: seen.append((p, m)))
    await FakeScript().run(ctx)
    assert seen == [(None, "대본을 생성하는 중…")]
