from app.constants import AssetKind, StageName
from app.providers.base import StageContext
from app.utils.errors import AppError


def input_audio_path(ctx: StageContext) -> str:
    """captions의 입력인 voice 단계 mp3의 저장소 상대 경로.

    없으면 AppError — run_stage의 except가 FAILED + 이 메시지로 흡수한다.
    """
    for asset in ctx.input_assets.get(StageName.VOICE, []):
        if asset["kind"] == AssetKind.AUDIO:
            return asset["path"]
    raise AppError(
        409, "VOICE_ASSET_MISSING", "음성 파일이 없습니다. voice 단계를 먼저 실행해 주세요."
    )
