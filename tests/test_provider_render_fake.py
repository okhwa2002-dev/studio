import pytest

from app.constants import AssetKind, StageName
from app.providers.base import REGISTRY, StageContext
from app.providers.render.fake import FakeRender
from app.utils import storage
from app.utils.errors import AppError

_ASSETS = {
    StageName.VOICE: [{"kind": AssetKind.AUDIO, "path": "projects/8/voice/voice.mp3", "meta": {}}],
    StageName.CAPTIONS: [{"kind": AssetKind.SRT, "path": "projects/8/captions/captions.srt", "meta": {}}],
}


def _ctx():
    return StageContext(topic="t", input_assets=_ASSETS, workdir="projects/8/render")


@pytest.mark.asyncio
async def test_fake_writes_mp4_and_output(monkeypatch, tmp_path):
    monkeypatch.setattr(storage, "_root", lambda: tmp_path)
    result = await FakeRender().run(_ctx())

    written = (tmp_path / "projects/8/render/render.mp4").read_bytes()
    assert len(written) > 0
    assert result.assets[0]["kind"] == AssetKind.VIDEO
    assert result.assets[0]["path"] == "projects/8/render/render.mp4"
    assert result.output["width"] == 1080
    assert result.output["height"] == 1920
    assert result.output["duration_sec"] is None  # no captions duration in this ctx -> None, key present


@pytest.mark.asyncio
async def test_fake_validates_inputs(monkeypatch, tmp_path):
    monkeypatch.setattr(storage, "_root", lambda: tmp_path)
    ctx = StageContext(topic="t", input_assets={}, workdir="projects/8/render")
    with pytest.raises(AppError) as exc:
        await FakeRender().run(ctx)
    assert exc.value.code == "VOICE_ASSET_MISSING"


def test_registry_has_render_fake():
    assert REGISTRY["render"]["fake"] is FakeRender
