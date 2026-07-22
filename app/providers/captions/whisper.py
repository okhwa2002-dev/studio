import asyncio
from functools import lru_cache

from app.config import get_settings
from app.constants import AssetKind
from app.providers.base import Provider, StageContext, StageResult
from app.providers.captions.audio import input_audio_path
from app.providers.captions.srt import to_srt
from app.utils import storage

_FILENAME = "captions.srt"
_DEVICE = "cpu"
_COMPUTE_TYPE = "int8"  # CPU에서 2배 이상 빠르고 한국어 품질 저하는 미미하다
_LANGUAGE = "ko"
_PROGRESS_MESSAGE = "받아쓰는 중…"


@lru_cache
def _load_model(model_size: str):
    """모델은 프로세스당 1회만 로드한다. 최초 1회는 자동 다운로드(~500MB)라 느리다."""
    from faster_whisper import WhisperModel

    return WhisperModel(model_size, device=_DEVICE, compute_type=_COMPUTE_TYPE)


def _transcribe(audio_path: str, model_size: str, on_progress) -> tuple[list[dict], str, float]:
    """오디오를 받아써 (단어들, 언어, 길이)를 돌려준다. CPU 블로킹 호출."""
    segments, info = _load_model(model_size).transcribe(
        audio_path, language=_LANGUAGE, word_timestamps=True
    )
    # segments는 지연 제너레이터다 — 이 스레드 안에서 끝까지 소비해야 한다.
    # 소비하면서 세그먼트 끝시각/전체 길이로 진행률을 보고한다.
    words: list[dict] = []
    for segment in segments:
        words.extend(
            {"w": word.word.strip(), "s": round(word.start, 3), "e": round(word.end, 3)}
            for word in (segment.words or [])
            if word.word.strip()
        )
        if info.duration:
            on_progress(min(100.0, segment.end / info.duration * 100), _PROGRESS_MESSAGE)
    return words, info.language, round(info.duration, 3)


class WhisperCaptions(Provider):
    """faster-whisper(로컬)로 mp3를 받아써 단어별 srt를 만드는 provider."""

    stage = "captions"
    name = "whisper"

    def __init__(self, transcribe=None):
        # 테스트는 가짜 transcribe를 주입해 모델·네트워크 없이 검증한다.
        self._transcribe = transcribe or _transcribe

    async def run(self, ctx: StageContext) -> StageResult:
        audio = storage.resolve(input_audio_path(ctx))
        model_size = get_settings().whisper_model
        # CPU를 수십 초 점유하는 블로킹 호출 — 이벤트 루프를 비켜준다.
        words, language, duration = await asyncio.to_thread(
            self._transcribe, str(audio), model_size, ctx.on_progress
        )

        rel = f"{ctx.workdir}/{_FILENAME}"
        size = storage.write_bytes(rel, to_srt(words).encode("utf-8"))
        return StageResult(
            output={
                "language": language,
                "duration_sec": duration,
                "word_count": len(words),
                "words": words,
            },
            assets=[
                {"kind": AssetKind.SRT, "path": rel, "meta": {"model": model_size, "size_bytes": size}}
            ],
        )
