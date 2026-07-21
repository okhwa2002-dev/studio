import pytest

from app.constants import AssetKind, StageName
from app.providers.base import REGISTRY, StageContext
from app.providers.captions.fake import FakeCaptions
from app.utils import storage
from app.utils.errors import AppError

_SCRIPT = {
    "title": "t",
    "hook": "훅",
    "scenes": [{"index": 1, "narration": "첫 문장 이다", "on_screen": "a"}],
    "estimated_duration_sec": 30,
}
_ASSETS = {StageName.VOICE: [{"kind": AssetKind.AUDIO, "path": "projects/7/voice/voice.mp3", "meta": {}}]}


def _ctx() -> StageContext:
    return StageContext(
        topic="t", inputs={"script": _SCRIPT}, input_assets=_ASSETS, workdir="projects/7/captions"
    )


@pytest.mark.asyncio
async def test_run_writes_srt_with_one_cue_per_word(monkeypatch, tmp_path):
    monkeypatch.setattr(storage, "_root", lambda: tmp_path)
    result = await FakeCaptions().run(_ctx())

    written = (tmp_path / "projects/7/captions/captions.srt").read_text(encoding="utf-8")
    assert written.count("-->") == 3  # "첫 문장 이다" → 단어 3개
    assert result.assets[0]["kind"] == AssetKind.SRT
    assert result.assets[0]["path"] == "projects/7/captions/captions.srt"


@pytest.mark.asyncio
async def test_output_carries_words_for_the_frontend(monkeypatch, tmp_path):
    monkeypatch.setattr(storage, "_root", lambda: tmp_path)
    result = await FakeCaptions().run(_ctx())

    assert result.output["word_count"] == 3
    assert [w["w"] for w in result.output["words"]] == ["첫", "문장", "이다"]
    assert result.output["words"][0]["s"] == 0.0
    assert result.output["duration_sec"] > 0


@pytest.mark.asyncio
async def test_missing_voice_asset_raises_apperror(monkeypatch, tmp_path):
    """voice 산출물이 없으면 run_stage의 except가 FAILED로 흡수할 AppError를 던진다."""
    monkeypatch.setattr(storage, "_root", lambda: tmp_path)
    ctx = StageContext(topic="t", inputs={"script": _SCRIPT}, input_assets={}, workdir="projects/8/captions")

    with pytest.raises(AppError) as exc:
        await FakeCaptions().run(ctx)
    assert exc.value.code == "VOICE_ASSET_MISSING"


def test_registry_has_fake_captions():
    assert REGISTRY["captions"]["fake"] is FakeCaptions
