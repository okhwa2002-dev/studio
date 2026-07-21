import pytest

from app.constants import AssetKind, StageName
from app.providers.base import StageContext
from app.providers.render.input import input_audio_path, input_srt_path
from app.utils.errors import AppError

_ASSETS = {
    StageName.VOICE: [{"kind": AssetKind.AUDIO, "path": "projects/5/voice/voice.mp3", "meta": {}}],
    StageName.CAPTIONS: [{"kind": AssetKind.SRT, "path": "projects/5/captions/captions.srt", "meta": {}}],
}


def _ctx(assets):
    return StageContext(topic="t", input_assets=assets, workdir="projects/5/render")


def test_resolves_audio_and_srt_relative_paths():
    ctx = _ctx(_ASSETS)
    assert input_audio_path(ctx) == "projects/5/voice/voice.mp3"
    assert input_srt_path(ctx) == "projects/5/captions/captions.srt"


def test_missing_voice_raises():
    with pytest.raises(AppError) as exc:
        input_audio_path(_ctx({StageName.CAPTIONS: _ASSETS[StageName.CAPTIONS]}))
    assert exc.value.code == "VOICE_ASSET_MISSING"


def test_missing_srt_raises():
    with pytest.raises(AppError) as exc:
        input_srt_path(_ctx({StageName.VOICE: _ASSETS[StageName.VOICE]}))
    assert exc.value.code == "CAPTIONS_ASSET_MISSING"
