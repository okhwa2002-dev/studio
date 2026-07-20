import pytest

from app.constants import AssetKind
from app.providers.base import REGISTRY, StageContext, get_provider
from app.providers.voice.fake import FakeVoice
from app.utils import storage

_SCRIPT = {
    "title": "바다 거북",
    "hook": "훅",
    "scenes": [
        {"index": 1, "narration": "첫 문장.", "on_screen": "a"},
        {"index": 2, "narration": "둘째 문장.", "on_screen": "b"},
    ],
    "estimated_duration_sec": 30,
}


@pytest.mark.asyncio
async def test_run_writes_file_and_returns_asset(monkeypatch, tmp_path):
    monkeypatch.setattr(storage, "_root", lambda: tmp_path)
    ctx = StageContext(topic="바다 거북", inputs={"script": _SCRIPT}, workdir="projects/1/voice")
    result = await FakeVoice().run(ctx)

    assert len(result.assets) == 1
    asset = result.assets[0]
    assert asset["kind"] == AssetKind.AUDIO
    assert asset["path"] == "projects/1/voice/voice.mp3"
    # 실제 파일이 저장됐고 크기가 output/meta와 일치한다
    written = (tmp_path / "projects/1/voice/voice.mp3").read_bytes()
    assert len(written) > 0
    assert asset["meta"]["size_bytes"] == len(written)
    assert result.output["size_bytes"] == len(written)


@pytest.mark.asyncio
async def test_run_reads_narration_from_script_input(monkeypatch, tmp_path):
    monkeypatch.setattr(storage, "_root", lambda: tmp_path)
    ctx = StageContext(topic="t", inputs={"script": _SCRIPT}, workdir="projects/2/voice")
    result = await FakeVoice().run(ctx)
    # 두 narration이 이어붙어 읽힌 글자수가 기록된다
    assert result.output["chars"] == len("첫 문장. 둘째 문장.")


def test_registry_has_voice_fake():
    assert REGISTRY["voice"]["fake"] is FakeVoice
    assert isinstance(get_provider("voice", "fake"), FakeVoice)
