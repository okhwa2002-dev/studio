import logging

from app.config import get_settings
from app.constants import AssetKind
from app.providers.base import Provider, StageContext, StageResult
from app.providers.render.input import input_audio_path, input_srt_path
from app.providers.render.sources import enabled_sources, queries_for, select_clip
from app.providers.render.timing import scene_spans
from app.utils import ffmpeg, storage
from app.utils.errors import AppError
from app.utils.stock.base import PHOTO
from app.utils.stock.download import download

logger = logging.getLogger(__name__)

_FILENAME = "render.mp4"
_SOURCES_DIR = "sources"
_WIDTH, _HEIGHT = 1080, 1920
_DOWNLOAD_SHARE = 40.0   # 진행률 0~40%는 소재 준비, 40~100%는 ffmpeg
_MAX_CLIP_TRIES = 3      # 한 씬에서 다운로드를 몇 번까지 다른 후보로 재시도할지


def _extension(kind: str) -> str:
    """저장 파일 확장자. ffmpeg가 실제 컨테이너를 스스로 판별하므로 대략만 맞으면 된다."""
    return ".jpg" if kind == PHOTO else ".mp4"


class StockRender(Provider):
    """Pexels·Pixabay 스톡 소재를 씬별 배경으로 깔아 9:16 mp4를 만드는 provider."""

    stage = "render"
    name = "stock"

    def __init__(self, runner=None, exe=None, sources=None, downloader=None):
        # 테스트는 fake runner/sources/downloader를 주입해 네트워크·ffmpeg 없이 검증한다.
        self._runner = runner or ffmpeg.run
        self._exe = exe
        self._sources = sources
        self._download = downloader or download

    def validate(self, settings: dict) -> None:
        enabled_sources()   # 키가 하나도 없으면 여기서 STOCK_API_KEY_MISSING → 실행 전 조기 실패

    def _exe_path(self) -> str:
        if self._exe is None:
            self._exe = ffmpeg.ffmpeg_exe()
        return self._exe

    async def _prepare_scene(self, ctx, sources, scene, index, seconds, used_keys, sources_dir):
        """씬 하나의 소재를 고르고 내려받는다. 실패한 후보는 건너뛰고 다음을 시도한다."""
        settings = get_settings()
        queries = queries_for(scene.get("on_screen", ""), ctx.topic)
        for _ in range(_MAX_CLIP_TRIES):
            clip, query = await select_clip(sources, queries, used_keys, ctx.attempt + index)
            used_keys.add(clip.key)   # 성공이든 실패든 이 후보는 다시 뽑지 않는다
            rel = f"{sources_dir}/scene{index + 1}{_extension(clip.kind)}"
            try:
                await self._download(
                    clip.url, rel, settings.stock_max_bytes, settings.stock_timeout_sec
                )
            except Exception:
                logger.warning("소재 내려받기 실패 — 다음 후보로: %s", clip.url, exc_info=True)
                continue
            return {"path": rel, "kind": clip.kind, "seconds": seconds,
                    "source": clip.source, "query": query,
                    "url": clip.page_url, "author": clip.author}
        raise AppError(502, "STOCK_DOWNLOAD_FAILED",
                       "배경 소재를 내려받지 못했습니다. 잠시 후 다시 시도해 주세요.")

    async def run(self, ctx: StageContext) -> StageResult:
        settings = get_settings()
        audio_abs = str(storage.resolve(input_audio_path(ctx)))
        srt_rel = input_srt_path(ctx)
        duration = ctx.inputs.get("captions", {}).get("duration_sec")
        scenes = (ctx.inputs.get("script") or {}).get("scenes") or []
        spans = scene_spans(scenes, duration)   # 씬·duration 검증도 여기서 함께 한다

        sources = self._sources or enabled_sources()
        sources_dir = f"{ctx.workdir}/{_SOURCES_DIR}"
        storage.clear_dir(sources_dir)   # 재생성 시 이전 소재를 남기지 않는다

        picked: list[dict] = []
        used_keys: set = set()
        for index, (scene, (start, end)) in enumerate(zip(scenes, spans)):
            ctx.on_progress(
                _DOWNLOAD_SHARE * index / len(scenes),
                f"배경 소재 준비 중… ({index + 1}/{len(scenes)})",
            )
            picked.append(await self._prepare_scene(
                ctx, sources, scene, index, end - start, used_keys, sources_dir
            ))

        out_rel = f"{ctx.workdir}/{_FILENAME}"
        cmd = ffmpeg.build_stock_cmd(
            exe=self._exe_path(),
            scenes=[{"path": p["path"], "kind": p["kind"], "seconds": p["seconds"]} for p in picked],
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

        def _ffmpeg_progress(percent, message):
            # ffmpeg의 0~100%를 전체 진행률 40~100% 구간으로 옮긴다.
            # percent가 0일 수도 있으므로 `if percent`가 아니라 None 비교여야 한다.
            scaled = None if percent is None else _DOWNLOAD_SHARE + (
                (100.0 - _DOWNLOAD_SHARE) * percent / 100.0
            )
            ctx.on_progress(scaled, message)

        # cwd를 저장소 루트로 둬야 상대경로 자막 필터가 동작한다(Windows ':' 회피).
        await self._runner(
            cmd, str(storage.resolve(".")), on_progress=_ffmpeg_progress, total_sec=duration
        )

        size = out_abs.stat().st_size
        return StageResult(
            output={
                "provider": "stock",
                "width": _WIDTH,
                "height": _HEIGHT,
                "duration_sec": duration,
                "size_bytes": size,
                "sources": [
                    {"scene": i + 1, "source": p["source"], "kind": p["kind"],
                     "query": p["query"], "url": p["url"], "author": p["author"]}
                    for i, p in enumerate(picked)
                ],
            },
            assets=[{"kind": AssetKind.VIDEO, "path": out_rel,
                     "meta": {"size_bytes": size, "width": _WIDTH, "height": _HEIGHT}}],
        )
