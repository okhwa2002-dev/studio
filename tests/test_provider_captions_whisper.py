import pytest

from app.constants import AssetKind, StageName
from app.providers.base import REGISTRY, StageContext
from app.providers.captions import whisper as whisper_module
from app.providers.captions.whisper import WhisperCaptions
from app.utils import storage
from app.utils.errors import AppError

_ASSETS = {StageName.VOICE: [{"kind": AssetKind.AUDIO, "path": "projects/9/voice/voice.mp3", "meta": {}}]}

_calls: list[dict] = []


def _fake_transcribe(audio_path: str, model_size: str, on_progress):
    _calls.append({"audio_path": audio_path, "model_size": model_size})
    on_progress(50.0, "받아쓰는 중…")
    words = [{"w": "안녕", "s": 0.0, "e": 0.5}, {"w": "하세요", "s": 0.5, "e": 1.1}]
    on_progress(100.0, "받아쓰는 중…")
    return words, "ko", 1.2


@pytest.fixture(autouse=True)
def _reset():
    _calls.clear()


def _ctx(on_progress=None) -> StageContext:
    kwargs = {"on_progress": on_progress} if on_progress else {}
    return StageContext(
        topic="t", input_assets=_ASSETS, workdir="projects/9/captions", **kwargs
    )


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


@pytest.mark.asyncio
async def test_run_forwards_progress_callback(monkeypatch, tmp_path):
    # 세그먼트를 소비할 때마다 "여기까지 왔다"가 밖으로 나가야 한다.
    monkeypatch.setattr(storage, "_root", lambda: tmp_path)
    seen: list[tuple[float | None, str]] = []
    await WhisperCaptions(transcribe=_fake_transcribe).run(
        _ctx(on_progress=lambda p, m: seen.append((p, m)))
    )
    assert seen == [(50.0, "받아쓰는 중…"), (100.0, "받아쓰는 중…")]


# ── 아래는 위 테스트들이 우회하는 실제 _transcribe(나눗셈/가드/클램프)를 직접 검증한다 ──
# 위 테스트는 전부 _fake_transcribe를 주입해 on_progress(50.0, ...) 같은 값을 하드코딩하므로
# 실제 percent 계산 코드는 한 줄도 실행되지 않는다. 여기서는 _load_model만 가짜로 바꿔
# 진짜 _transcribe 함수(모듈 레벨)를 그대로 호출한다.


class _FakeWord:
    def __init__(self, word: str, start: float, end: float):
        self.word = word
        self.start = start
        self.end = end


class _FakeSegment:
    def __init__(self, end: float, words: list[_FakeWord]):
        self.end = end
        self.words = words


class _FakeWhisperInfo:
    def __init__(self, duration: float, language: str = "ko"):
        self.duration = duration
        self.language = language


class _FakeWhisperModel:
    """faster_whisper.WhisperModel 흉내 — transcribe()가 (segments, info)를 돌려준다."""

    def __init__(self, segments, info):
        self._segments = segments
        self._info = info

    def transcribe(self, audio_path, **kwargs):
        return self._segments, self._info


def _patch_load_model(monkeypatch, segments, info):
    # _load_model은 lru_cache로 감싸져 있으므로 캐시를 거치지 않게 모듈 속성 자체를 바꿔치기한다.
    monkeypatch.setattr(whisper_module, "_load_model", lambda model_size: _FakeWhisperModel(segments, info))


def test_transcribe_reports_ascending_percent_and_words(monkeypatch):
    segments = [
        _FakeSegment(0.6, [_FakeWord("안녕", 0.0, 0.6)]),
        _FakeSegment(1.2, [_FakeWord("하세요", 0.6, 1.2)]),
    ]
    _patch_load_model(monkeypatch, segments, _FakeWhisperInfo(duration=1.2, language="ko"))
    seen: list[tuple[float | None, str]] = []

    words, language, duration = whisper_module._transcribe(
        "audio.mp3", "small", lambda p, m: seen.append((p, m))
    )

    assert seen == [(50.0, "받아쓰는 중…"), (100.0, "받아쓰는 중…")]
    assert words == [
        {"w": "안녕", "s": 0.0, "e": 0.6},
        {"w": "하세요", "s": 0.6, "e": 1.2},
    ]
    assert language == "ko"
    assert duration == 1.2


def test_transcribe_duration_zero_skips_progress_without_raising(monkeypatch):
    # info.duration이 0.0이면 나눗셈을 하면 ZeroDivisionError다 — 가드는 이 세그먼트의
    # 진행률 보고를 통째로 건너뛰어야 한다(0.0을 보고하는 게 아니라 아예 호출 안 함).
    segments = [_FakeSegment(0.0, [_FakeWord("x", 0.0, 0.0)])]
    _patch_load_model(monkeypatch, segments, _FakeWhisperInfo(duration=0.0, language="ko"))
    seen: list[tuple[float | None, str]] = []

    words, _language, duration = whisper_module._transcribe(
        "audio.mp3", "small", lambda p, m: seen.append((p, m))
    )

    assert seen == []
    assert duration == 0.0
    assert words == [{"w": "x", "s": 0.0, "e": 0.0}]


def test_transcribe_clamps_percent_at_100(monkeypatch):
    # segment.end가 info.duration을 넘어서도(위스퍼가 실제로 이런 값을 낼 수 있다)
    # 보고되는 퍼센트는 100.0을 절대 넘으면 안 된다.
    segments = [_FakeSegment(1.5, [_FakeWord("x", 1.0, 1.5)])]
    _patch_load_model(monkeypatch, segments, _FakeWhisperInfo(duration=1.2, language="ko"))
    seen: list[tuple[float | None, str]] = []

    whisper_module._transcribe("audio.mp3", "small", lambda p, m: seen.append((p, m)))

    assert seen == [(100.0, "받아쓰는 중…")]
    assert seen[0][0] <= 100.0


def test_transcribe_drains_lazy_generator_fully(monkeypatch):
    # segments가 진짜 제너레이터일 때도 for 루프가 끝까지(StopIteration까지) 소비해야 한다.
    # 루프 안에 early return이 생기면 drained가 채워지지 않거나 뒤 세그먼트 단어가 빠진다.
    drained: list[bool] = []

    def _lazy_segments():
        yield _FakeSegment(1.0, [_FakeWord("a", 0.0, 1.0)])
        yield _FakeSegment(2.0, [_FakeWord("b", 1.0, 2.0)])
        yield _FakeSegment(3.0, [_FakeWord("c", 2.0, 3.0)])
        drained.append(True)  # for 루프가 마지막 yield 다음 next()까지 호출해야만 실행된다

    _patch_load_model(monkeypatch, _lazy_segments(), _FakeWhisperInfo(duration=3.0, language="ko"))

    words, _language, _duration = whisper_module._transcribe("audio.mp3", "small", lambda p, m: None)

    assert drained == [True]
    assert [w["w"] for w in words] == ["a", "b", "c"]
