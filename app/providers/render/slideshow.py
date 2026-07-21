from app.config import get_settings
from app.constants import AssetKind
from app.providers.base import Provider, StageContext, StageResult
from app.providers.render.input import input_audio_path, input_srt_path
from app.utils import ffmpeg, storage

_FILENAME = "render.mp4"
_WIDTH, _HEIGHT = 1080, 1920


class SlideshowRender(Provider):
    """단색 배경 + 단어별 자막 번인 + 오디오로 9:16 mp4를 만드는 provider."""

    stage = "render"
    name = "slideshow"

    def __init__(self, runner=None, exe=None):
        # 테스트는 fake runner/exe를 주입해 ffmpeg 없이 검증한다.
        self._runner = runner or ffmpeg.run
        self._exe = exe

    def _exe_path(self) -> str:
        if self._exe is None:
            self._exe = ffmpeg.ffmpeg_exe()
        return self._exe

    async def run(self, ctx: StageContext) -> StageResult:
        settings = get_settings()
        audio_abs = str(storage.resolve(input_audio_path(ctx)))
        srt_rel = input_srt_path(ctx)
        out_rel = f"{ctx.workdir}/{_FILENAME}"

        cmd = ffmpeg.build_slideshow_cmd(
            exe=self._exe_path(),
            bg_color=settings.render_bg_color,
            audio_abs=audio_abs,
            srt_rel=srt_rel,
            out_rel=out_rel,
            width=_WIDTH,
            height=_HEIGHT,
            font=settings.render_font,
            font_size=settings.render_font_size,
        )
        out_abs = storage.resolve(out_rel)
        out_abs.parent.mkdir(parents=True, exist_ok=True)

        # cwd를 저장소 루트로 둬야 상대경로 자막 필터가 동작한다(Windows ':' 회피).
        await self._runner(cmd, str(storage.resolve(".")))

        size = out_abs.stat().st_size
        duration = ctx.inputs.get("captions", {}).get("duration_sec")
        return StageResult(
            output={
                "provider": "slideshow",
                "width": _WIDTH,
                "height": _HEIGHT,
                "duration_sec": duration,
                "size_bytes": size,
            },
            assets=[{"kind": AssetKind.VIDEO, "path": out_rel,
                     "meta": {"size_bytes": size, "width": _WIDTH, "height": _HEIGHT}}],
        )
