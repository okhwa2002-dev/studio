import pytest

from app.constants import AssetKind, StageName
from app.providers.base import REGISTRY, StageContext
from app.providers.render.slideshow import SlideshowRender
from app.utils import storage
from app.utils.errors import AppError

_ASSETS = {
    StageName.VOICE: [{"kind": AssetKind.AUDIO, "path": "projects/9/voice/voice.mp3", "meta": {}}],
    StageName.CAPTIONS: [{"kind": AssetKind.SRT, "path": "projects/9/captions/captions.srt", "meta": {}}],
}
_INPUTS = {"captions": {"duration_sec": 3.5}}

_calls: list[dict] = []


async def _fake_runner(cmd, cwd):
    _calls.append({"cmd": cmd, "cwd": cwd})
    # 진짜 ffmpeg가 out_rel(마지막 인자)에 쓰듯, 파일을 남겨 provider가 크기를 잰다.
    storage.write_bytes(cmd[-1], b"MP4-bytes")


@pytest.fixture(autouse=True)
def _reset():
    _calls.clear()


def _ctx():
    return StageContext(topic="t", inputs=_INPUTS, input_assets=_ASSETS, workdir="projects/9/render")


@pytest.mark.asyncio
async def test_run_invokes_ffmpeg_and_records_video_asset(monkeypatch, tmp_path):
    monkeypatch.setattr(storage, "_root", lambda: tmp_path)
    provider = SlideshowRender(runner=_fake_runner, exe="/bin/ffmpeg")
    result = await provider.run(_ctx())

    assert result.assets[0]["kind"] == AssetKind.VIDEO
    assert result.assets[0]["path"] == "projects/9/render/render.mp4"
    assert result.output["width"] == 1080
    assert result.output["height"] == 1920
    assert result.output["duration_sec"] == 3.5
    assert result.output["size_bytes"] == len(b"MP4-bytes")


@pytest.mark.asyncio
async def test_run_uses_storage_root_as_cwd_and_relative_srt(monkeypatch, tmp_path):
    monkeypatch.setattr(storage, "_root", lambda: tmp_path)
    await SlideshowRender(runner=_fake_runner, exe="/bin/ffmpeg").run(_ctx())

    call = _calls[0]
    assert call["cwd"] == str(tmp_path)  # 상대경로 필터를 위해 루트에서 실행
    vf = call["cmd"][call["cmd"].index("-vf") + 1]
    assert "subtitles=projects/9/captions/captions.srt" in vf
    # 오디오는 절대경로 입력
    assert str(tmp_path / "projects/9/voice/voice.mp3") in call["cmd"]


@pytest.mark.asyncio
async def test_missing_srt_raises(monkeypatch, tmp_path):
    monkeypatch.setattr(storage, "_root", lambda: tmp_path)
    ctx = StageContext(topic="t", inputs=_INPUTS,
                       input_assets={StageName.VOICE: _ASSETS[StageName.VOICE]},
                       workdir="projects/9/render")
    with pytest.raises(AppError) as exc:
        await SlideshowRender(runner=_fake_runner, exe="/bin/ffmpeg").run(ctx)
    assert exc.value.code == "CAPTIONS_ASSET_MISSING"


def test_registry_has_render_slideshow():
    assert REGISTRY["render"]["slideshow"] is SlideshowRender
