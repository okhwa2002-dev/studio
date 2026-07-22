import pytest

from app.constants import AssetKind
from app.providers.base import REGISTRY, StageContext
from app.providers.voice.edge_tts import EdgeTTS
from app.utils import storage

_SCRIPT = {
    "title": "t",
    "hook": "훅",
    "scenes": [{"index": 1, "narration": "첫 문장.", "on_screen": "a"}],
    "estimated_duration_sec": 30,
}


class _FakeCommunicate:
    """edge_tts.Communicate 흉내 — stream()이 audio 청크를 내놓는다."""

    created: list[dict] = []

    def __init__(self, text, voice, **kwargs):
        type(self).created.append({"text": text, "voice": voice})

    async def stream(self):
        yield {"type": "audio", "data": b"ID3-fake-"}
        yield {"type": "WordBoundary"}  # 오디오가 아닌 청크는 무시돼야 한다
        yield {"type": "audio", "data": b"audio"}


@pytest.fixture(autouse=True)
def _reset():
    _FakeCommunicate.created = []


@pytest.mark.asyncio
async def test_run_streams_audio_to_file(monkeypatch, tmp_path):
    monkeypatch.setattr(storage, "_root", lambda: tmp_path)
    ctx = StageContext(topic="t", inputs={"script": _SCRIPT}, workdir="projects/3/voice")
    result = await EdgeTTS(communicate_factory=_FakeCommunicate).run(ctx)

    written = (tmp_path / "projects/3/voice/voice.mp3").read_bytes()
    assert written == b"ID3-fake-audio"  # audio 청크만 이어붙는다
    assert result.assets[0]["kind"] == AssetKind.AUDIO
    assert result.assets[0]["path"] == "projects/3/voice/voice.mp3"
    assert result.assets[0]["meta"]["size_bytes"] == len(written)


@pytest.mark.asyncio
async def test_run_passes_narration_and_korean_voice(monkeypatch, tmp_path):
    monkeypatch.setattr(storage, "_root", lambda: tmp_path)
    ctx = StageContext(topic="t", inputs={"script": _SCRIPT}, workdir="projects/4/voice")
    await EdgeTTS(communicate_factory=_FakeCommunicate).run(ctx)

    call = _FakeCommunicate.created[0]
    assert call["text"] == "첫 문장."
    assert call["voice"] == "ko-KR-SunHiNeural"


def test_registry_has_edge_tts():
    assert REGISTRY["voice"]["edge_tts"] is EdgeTTS


@pytest.mark.asyncio
async def test_run_reports_message_without_percent(monkeypatch, tmp_path):
    # edge-tts는 전체 길이를 알려주지 않는다 — 진짜 %가 없으므로 None을 보낸다.
    monkeypatch.setattr(storage, "_root", lambda: tmp_path)
    seen: list[tuple[float | None, str]] = []
    ctx = StageContext(
        topic="t", inputs={"script": _SCRIPT}, workdir="projects/5/voice",
        on_progress=lambda p, m: seen.append((p, m)),
    )
    await EdgeTTS(communicate_factory=_FakeCommunicate).run(ctx)
    assert seen == [(None, "음성 합성 중…")]
