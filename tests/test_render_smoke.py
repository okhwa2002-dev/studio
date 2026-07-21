import wave

import pytest

from app.constants import AssetKind, StageName
from app.providers.base import StageContext
from app.providers.render.slideshow import SlideshowRender
from app.utils import storage


def _write_wav(path):
    path.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(path), "w") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(16000)
        w.writeframes(b"\x00\x00" * 16000)  # 1초 무음


@pytest.mark.slow
@pytest.mark.asyncio
async def test_real_ffmpeg_produces_playable_mp4(monkeypatch, tmp_path):
    monkeypatch.setattr(storage, "_root", lambda: tmp_path)
    _write_wav(tmp_path / "projects/1/voice/voice.mp3")  # 확장자만 mp3, 내용은 wav여도 ffmpeg가 읽음
    storage.write_bytes("projects/1/captions/captions.srt",
                        "1\n00:00:00,000 --> 00:00:01,000\n안녕하세요\n".encode("utf-8"))

    ctx = StageContext(
        topic="t",
        inputs={"captions": {"duration_sec": 1.0}},
        input_assets={
            StageName.VOICE: [{"kind": AssetKind.AUDIO, "path": "projects/1/voice/voice.mp3", "meta": {}}],
            StageName.CAPTIONS: [{"kind": AssetKind.SRT, "path": "projects/1/captions/captions.srt", "meta": {}}],
        },
        workdir="projects/1/render",
    )
    result = await SlideshowRender().run(ctx)  # 실제 번들 ffmpeg 사용

    out = tmp_path / "projects/1/render/render.mp4"
    assert out.exists() and out.stat().st_size > 0
    assert result.assets[0]["kind"] == AssetKind.VIDEO
    print(f"\n[스모크] 생성됨: {out} ({out.stat().st_size} bytes) — 자막·폰트 육안 확인")
