from app.constants import AssetKind
from app.providers.base import Provider, StageContext, StageResult
from app.providers.voice.text import narration_text
from app.utils import storage

_FILENAME = "voice.mp3"


class FakeVoice(Provider):
    """외부 호출 없이 결정적 더미 오디오를 만드는 개발/테스트용 provider."""

    stage = "voice"
    name = "fake"

    async def run(self, ctx: StageContext) -> StageResult:
        text = narration_text(ctx.inputs)
        # 실제 mp3는 아니지만 "글자수만큼의 결정적 바이트"라 크기·교체를 검증하기 충분하다.
        data = (f"FAKE-AUDIO[{ctx.attempt}]:{text}").encode("utf-8")
        rel = f"{ctx.workdir}/{_FILENAME}"
        size = storage.write_bytes(rel, data)
        meta = {"voice": "fake", "size_bytes": size}
        return StageResult(
            output={"voice": "fake", "size_bytes": size, "chars": len(text)},
            assets=[{"kind": AssetKind.AUDIO, "path": rel, "meta": meta}],
        )
