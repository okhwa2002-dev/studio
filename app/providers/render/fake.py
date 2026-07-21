from app.constants import AssetKind
from app.providers.base import Provider, StageContext, StageResult
from app.providers.render.input import input_audio_path, input_srt_path
from app.utils import storage

_FILENAME = "render.mp4"
_WIDTH, _HEIGHT = 1080, 1920


class FakeRender(Provider):
    """ffmpeg 없이 결정적 더미 mp4를 만드는 개발/테스트용 provider."""

    stage = "render"
    name = "fake"

    async def run(self, ctx: StageContext) -> StageResult:
        # 실제로 합성하진 않지만 입력 계약은 진짜 provider와 똑같이 검증한다.
        input_audio_path(ctx)
        input_srt_path(ctx)
        data = (f"FAKE-VIDEO[{ctx.attempt}]").encode("utf-8")
        rel = f"{ctx.workdir}/{_FILENAME}"
        size = storage.write_bytes(rel, data)
        return StageResult(
            output={"provider": "fake", "width": _WIDTH, "height": _HEIGHT, "size_bytes": size},
            assets=[{"kind": AssetKind.VIDEO, "path": rel, "meta": {"size_bytes": size}}],
        )
