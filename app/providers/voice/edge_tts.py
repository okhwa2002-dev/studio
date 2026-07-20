from app.constants import AssetKind
from app.providers.base import Provider, StageContext, StageResult
from app.providers.voice.text import narration_text
from app.utils import storage

_MODEL_VOICE = "ko-KR-SunHiNeural"  # 한국어 기본 목소리 (선택 UI는 다음 슬라이스)
_FILENAME = "voice.mp3"


class EdgeTTS(Provider):
    """edge-tts(무료·API 키 불필요)로 대본을 읽어 mp3를 만드는 provider."""

    stage = "voice"
    name = "edge_tts"

    def __init__(self, communicate_factory=None):
        # 테스트는 가짜 factory를 주입해 네트워크 없이 검증한다.
        self._communicate_factory = communicate_factory

    def _factory(self):
        if self._communicate_factory is None:
            # 파일명이 edge_tts.py지만 절대 import라 설치된 edge_tts 패키지를 가져온다.
            from edge_tts import Communicate

            self._communicate_factory = Communicate
        return self._communicate_factory

    async def run(self, ctx: StageContext) -> StageResult:
        text = narration_text(ctx.inputs)
        communicate = self._factory()(text, _MODEL_VOICE)
        chunks = bytearray()
        async for chunk in communicate.stream():
            if chunk.get("type") == "audio":
                chunks += chunk["data"]

        rel = f"{ctx.workdir}/{_FILENAME}"
        size = storage.write_bytes(rel, bytes(chunks))
        meta = {"voice": _MODEL_VOICE, "size_bytes": size}
        return StageResult(
            output={"voice": _MODEL_VOICE, "size_bytes": size, "chars": len(text)},
            assets=[{"kind": AssetKind.AUDIO, "path": rel, "meta": meta}],
        )
