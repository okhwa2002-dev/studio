import pytest

from app.constants import AssetKind, StageName
from app.providers.base import REGISTRY, StageContext
from app.providers.captions.whisper import WhisperCaptions
from app.utils import storage
from app.utils.errors import AppError

_ASSETS = {StageName.VOICE: [{"kind": AssetKind.AUDIO, "path": "projects/9/voice/voice.mp3", "meta": {}}]}

_calls: list[dict] = []


def _fake_transcribe(audio_path: str, model_size: str):
    _calls.append({"audio_path": audio_path, "model_size": model_size})
    words = [{"w": "안녕", "s": 0.0, "e": 0.5}, {"w": "하세요", "s": 0.5, "e": 1.1}]
    return words, "ko", 1.2


@pytest.fixture(autouse=True)
def _reset():
    _calls.clear()


def _ctx() -> StageContext:
    return StageContext(topic="t", input_assets=_ASSETS, workdir="projects/9/captions")


@pytest.mark.asyncio
async def test_run_writes_srt_and_output(monkeypatch, tmp_path):
    monkeypatch.setattr(storage, "_root", lambda: tmp_path)
    result = await WhisperCaptions(transcribe=_fake_transcribe).run(_ctx())

    written = (tmp_path / "projects/9/captions/captions.srt").read_text(encoding="utf-8")
    assert written.startswith("1\n00:00:00,000 --> 00:00:00,500\n안녕\n")
    assert result.output == {
        "language": "ko",
        "duration_sec": 1.2,
        "word_count": 2,
        "words": [{"w": "안녕", "s": 0.0, "e": 0.5}, {"w": "하세요", "s": 0.5, "e": 1.1}],
    }
    assert result.assets[0]["kind"] == AssetKind.SRT
    assert result.assets[0]["path"] == "projects/9/captions/captions.srt"


@pytest.mark.asyncio
async def test_run_passes_absolute_audio_path_and_model_size(monkeypatch, tmp_path):
    monkeypatch.setattr(storage, "_root", lambda: tmp_path)
    await WhisperCaptions(transcribe=_fake_transcribe).run(_ctx())

    # provider는 저장소 상대 경로를 절대 경로로 풀어 넘겨야 한다(whisper는 실제 파일을 연다)
    assert _calls[0]["audio_path"] == str(tmp_path / "projects/9/voice/voice.mp3")
    assert _calls[0]["model_size"] == "small"  # 설정 기본값


@pytest.mark.asyncio
async def test_missing_voice_asset_raises_apperror(monkeypatch, tmp_path):
    monkeypatch.setattr(storage, "_root", lambda: tmp_path)
    ctx = StageContext(topic="t", input_assets={}, workdir="projects/9/captions")

    with pytest.raises(AppError) as exc:
        await WhisperCaptions(transcribe=_fake_transcribe).run(ctx)
    assert exc.value.code == "VOICE_ASSET_MISSING"


def test_registry_has_whisper():
    assert REGISTRY["captions"]["whisper"] is WhisperCaptions
