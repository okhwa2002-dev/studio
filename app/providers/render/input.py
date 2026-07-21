from app.constants import AssetKind, StageName
from app.providers.base import StageContext
from app.utils.errors import AppError


def _find(ctx: StageContext, stage: str, kind: str) -> str | None:
    for asset in ctx.input_assets.get(stage, []):
        if asset["kind"] == kind:
            return asset["path"]
    return None


def input_audio_path(ctx: StageContext) -> str:
    """render의 입력인 voice mp3의 저장소 상대 경로. 없으면 AppError → FAILED."""
    path = _find(ctx, StageName.VOICE, AssetKind.AUDIO)
    if path is None:
        raise AppError(409, "VOICE_ASSET_MISSING", "음성 파일이 없습니다. voice 단계를 먼저 실행해 주세요.")
    return path


def input_srt_path(ctx: StageContext) -> str:
    """render의 입력인 captions srt의 저장소 상대 경로. 없으면 AppError → FAILED."""
    path = _find(ctx, StageName.CAPTIONS, AssetKind.SRT)
    if path is None:
        raise AppError(409, "CAPTIONS_ASSET_MISSING", "자막 파일이 없습니다. captions 단계를 먼저 실행해 주세요.")
    return path
