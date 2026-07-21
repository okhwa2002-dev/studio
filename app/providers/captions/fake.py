from app.constants import AssetKind
from app.providers.base import Provider, StageContext, StageResult
from app.providers.captions.audio import input_audio_path
from app.providers.captions.srt import to_srt
from app.providers.voice.text import narration_text
from app.utils import storage

_FILENAME = "captions.srt"
_SEC_PER_WORD = 0.4  # 단어마다 균등 배분 — 결정적이라 테스트가 흔들리지 않는다


class FakeCaptions(Provider):
    """whisper 없이 대본을 단어로 쪼개 결정적 자막을 만드는 개발/테스트용 provider."""

    stage = "captions"
    name = "fake"

    async def run(self, ctx: StageContext) -> StageResult:
        # 오디오 바이트를 읽지는 않지만, 입력 계약은 진짜 provider와 똑같이 검증한다.
        input_audio_path(ctx)
        words = [
            {"w": word, "s": round(i * _SEC_PER_WORD, 3), "e": round((i + 1) * _SEC_PER_WORD, 3)}
            for i, word in enumerate(narration_text(ctx.inputs).split())
        ]
        rel = f"{ctx.workdir}/{_FILENAME}"
        size = storage.write_bytes(rel, to_srt(words).encode("utf-8"))
        return StageResult(
            output={
                "language": "ko",
                "duration_sec": round(len(words) * _SEC_PER_WORD, 3),
                "word_count": len(words),
                "words": words,
            },
            assets=[{"kind": AssetKind.SRT, "path": rel, "meta": {"model": "fake", "size_bytes": size}}],
        )
